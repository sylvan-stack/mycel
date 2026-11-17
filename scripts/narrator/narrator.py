"""Write source-grounded summaries for Mycel's optional RAPTOR command."""

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import tempfile
import time
from typing import BinaryIO, TypedDict


REQUEST_CHARACTERS = 48_000
REQUEST_BYTES = REQUEST_CHARACTERS * 4
PASSAGE_CHARACTERS = 1_600
PACKAGED_PROMPTS = Path(__file__).resolve().parents[2] / "src/mycel/data/summary-prompts.json"
SECTION_PLACE = re.compile(r"[^\r\n\0]+ › [^\r\n\0]*")
CUT_LINE = re.compile(r"^\[Mycel: source text cut at request limit\]\r?$", re.MULTILINE)
PARAGRAPH_GAP = re.compile(r"\r?\n(?:[ \t]*\r?\n)+")
JSON_FENCE = re.compile(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", re.DOTALL)
ATTEMPT_SECONDS = 270
TEXT_LIMIT = 8
EMBEDDING_LIMIT = 1
MODEL_OUTPUT_BYTES = 1024 * 1024
EMBEDDING_OUTPUT_BYTES = 8 * 1024 * 1024
MODEL_STDERR_BYTES = 64 * 1024


class NarratorError(Exception):
    """A writer failure that can be reported without source or provider data."""


class BudgetExhausted(NarratorError):
    """The attempt cannot start or accept another request."""


class FormatError(NarratorError):
    """The command returned a response outside the requested format."""


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


@contextmanager
def _interrupt_on_termination():
    # Mycel terminates the writer's group. Translate that signal into a Python
    # interruption so we also reap the isolated model command's group.
    def stop(_signum, _frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def _time_left(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise BudgetExhausted("writer time limit reached")
    return remaining


def _child_environment(directory: str) -> dict[str, str]:
    return {
        "HOME": str(Path.home().resolve()),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "TMPDIR": directory,
    }


def _stop_command(process: subprocess.Popen[bytes], inherit_group: bool) -> None:
    try:
        if inherit_group:
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _drain(
    process: subprocess.Popen[bytes], payload: bytes, deadline: float, limit: int,
    inherit_group: bool,
) -> bytes:
    stdin, stdout, stderr = process.stdin, process.stdout, process.stderr
    assert stdin is not None and stdout is not None and stderr is not None
    pending = memoryview(payload)
    output = bytearray()
    stderr_bytes = 0
    descendants_stopped = False
    with selectors.DefaultSelector() as selector:
        for stream in (stdin, stdout, stderr):
            os.set_blocking(stream.fileno(), False)
        selector.register(stdout, selectors.EVENT_READ)
        selector.register(stderr, selectors.EVENT_READ)
        if pending:
            selector.register(stdin, selectors.EVENT_WRITE)
        else:
            stdin.close()
        while selector.get_map() or process.poll() is None:
            if not descendants_stopped and process.poll() is not None:
                _stop_command(process, inherit_group)
                descendants_stopped = True
            for key, _ in selector.select(min(0.05, _time_left(deadline))):
                stream = key.fileobj
                try:
                    if stream is stdin:
                        written = os.write(stdin.fileno(), pending[:65536])
                        pending = pending[written:]
                        if pending:
                            continue
                    else:
                        chunk = os.read(stream.fileno(), 65536)
                        if chunk:
                            if stream is stdout:
                                if len(output) + len(chunk) > limit:
                                    raise NarratorError("command output exceeds its limit")
                                output.extend(chunk)
                            else:
                                stderr_bytes += len(chunk)
                                if stderr_bytes > MODEL_STDERR_BYTES:
                                    raise NarratorError("command diagnostics exceed their limit")
                            continue
                except BlockingIOError:
                    continue
                selector.unregister(stream)
                stream.close()
    _time_left(deadline)
    if process.wait() != 0:
        raise NarratorError("configured command failed")
    return bytes(output)


def _run_command(
    argv: tuple[str, ...], payload: bytes, deadline: float, *,
    output_limit: int = MODEL_OUTPUT_BYTES, inherit_group: bool = False,
) -> bytes:
    """Run literal argv and accept one complete, bounded command response."""
    _time_left(deadline)
    if not argv or not Path(argv[0]).is_absolute():
        raise NarratorError("configured command requires an absolute executable")
    try:
        with tempfile.TemporaryDirectory(prefix="narrator-child-") as directory:
            with subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=directory, env=_child_environment(directory), close_fds=True,
                start_new_session=not inherit_group,
            ) as process:
                try:
                    response = _drain(process, payload, deadline, output_limit, inherit_group)
                finally:
                    _stop_command(process, inherit_group)
                _time_left(deadline)
                return response
    except (OSError, ValueError):
        raise NarratorError("configured command could not exchange data") from None


def _json_value(data: bytes | str) -> object:
    try:
        text = data.decode("utf-8") if isinstance(data, bytes) else data
        text = text.strip()
        fenced = JSON_FENCE.fullmatch(text)
        return json.loads(fenced[1] if fenced else text)
    except (ValueError, RecursionError):
        raise FormatError("command response is not valid JSON") from None


def _metered_value(response: bytes, event: dict[str, object]) -> object:
    decoded = _json_value(response)
    if not isinstance(decoded, dict) or set(decoded) != {"response", "usage"}:
        return decoded
    usage = decoded["usage"]
    if usage is not None:
        fields = {"input_tokens", "output_tokens", "total_tokens"}
        if (
            not isinstance(usage, dict) or not usage or not usage.keys() <= fields
            or any(type(count) is not int or count < 0 for count in usage.values())
        ):
            raise FormatError("command usage is not valid")
        event["usage"] = usage
    value = decoded["response"]
    return _json_value(value) if isinstance(value, str) else value


@dataclass
class Meter:
    deadline: float
    text_calls: int = 0
    embedding_calls: int = 0
    events: list[dict[str, object]] = field(default_factory=list)

    def admit_repair(self) -> bool:
        return self.text_calls <= TEXT_LIMIT - 2 and time.monotonic() < self.deadline

    def call[T](
        self, argv: tuple[str, ...], payload: bytes, stage: str,
        validate: Callable[[object], T], *, embedding: bool = False,
    ) -> T:
        _time_left(self.deadline)
        if embedding:
            if self.embedding_calls >= EMBEDDING_LIMIT:
                raise BudgetExhausted("embedding request limit reached")
            self.embedding_calls += 1
        else:
            if self.text_calls >= TEXT_LIMIT:
                raise BudgetExhausted("text request limit reached")
            self.text_calls += 1
        event: dict[str, object] = {"stage": stage, "outcome": "failed", "usage": None}
        self.events.append(event)
        started = time.monotonic()
        try:
            output_limit = EMBEDDING_OUTPUT_BYTES if embedding else MODEL_OUTPUT_BYTES
            response = _run_command(argv, payload, self.deadline, output_limit=output_limit)
            value = _metered_value(response, event)
            try:
                result = validate(value)
            except ValueError:
                raise FormatError("command response has an invalid structure") from None
            _time_left(self.deadline)
        except FormatError:
            event["outcome"] = "format_error"
            raise
        except BudgetExhausted:
            event["outcome"] = "budget_exhausted"
            raise
        else:
            event["outcome"] = "accepted"
            return result
        finally:
            event["seconds"] = time.monotonic() - started

    def text[T](
        self, argv: tuple[str, ...], stage: str, instructions: str, payload: object,
        validate: Callable[[object], T], *, retry: bool = False,
    ) -> T:
        data = json.dumps(payload, ensure_ascii=False)
        request = instructions.rstrip() + "\n\n"
        try:
            return self.call(argv, (request + data).encode("utf-8"), stage, validate)
        except FormatError:
            if not retry:
                raise
        correction = "The preceding response had the wrong format. Return valid JSON in the requested shape."
        return self.call(argv, (request + correction + "\n\n" + data).encode("utf-8"), stage, validate)
