"""Deterministic framing for the standalone Narrator compatibility input."""

from dataclasses import dataclass
from hashlib import sha256

from ._embedding_plan import document_place_line
from ._errors import MycelError
from ._resolver import SelectionMember, _validate_chunk
from ._source_refs import SourceAddress


REQUEST_LIMIT = 48_000
CUT_NOTICE = "[Mycel: source text cut at request limit]"
SEPARATOR = "\n\n---\n\n"


def _settings():
    raise MycelError("settings", "The summary instruction/task framing is invalid or unavailable.")


@dataclass(frozen=True)
class SummaryPrompts:
    instruction: bytes
    task: bytes
    profile: str

    def __post_init__(self):
        try:
            if type(self.instruction) is not bytes or type(self.task) is not bytes:
                _settings()
            instruction, task = self.instruction.decode("utf-8").strip(), self.task.decode("utf-8").strip()
            if (not instruction or not task or "\0" in instruction + task
                    or task.count("$sections") != 1 or not isinstance(self.profile, str)
                    or not self.profile or "\0" in self.profile
                    or len(instruction + "\n\n" + task.replace("$sections", "")) >= REQUEST_LIMIT):
                _settings()
        except UnicodeError:
            _settings()

    def render(self, sections: str) -> str:
        return self.instruction.decode("utf-8").strip() + "\n\n" + self.task.decode("utf-8").strip().replace("$sections", sections)

    @property
    def hashes(self):
        return {"instruction": sha256(self.instruction).hexdigest(), "task": sha256(self.task).hexdigest()}


@dataclass(frozen=True)
class SummarySection:
    member: SelectionMember
    position: int

    def __post_init__(self):
        if not isinstance(self.member, SelectionMember) or type(self.position) is not int or self.position < 0:
            raise MycelError("invalid_input", "The summary section is invalid.")
        _validate_chunk(self.member.chunk)
        if (not isinstance(self.member.place, SourceAddress) or self.member.place.name is None
                or self.member.place.name != self.member.chunk.name
                or self.member.chunk.kind not in {"document", "summary"}
                or (self.member.place.root == "index") != (self.member.chunk.kind == "summary")):
            raise MycelError("invalid_input", "The summary section has an invalid place or kind.")
        try:
            self.member.chunk.source.decode("utf-8")
            document_place_line(self.member.place.path, self.member.place.name or self.member.chunk.name)
        except (UnicodeError, ValueError):
            raise MycelError("invalid_input", "The summary section is not valid UTF-8 evidence.") from None

    @property
    def place_line(self) -> str:
        return document_place_line(self.member.place.path, self.member.place.name or self.member.chunk.name)

    @property
    def order(self):
        place, chunk = self.member.place, self.member.chunk
        return (place.root, place.path, self.position, place.address, chunk.identifier)


@dataclass(frozen=True)
class SummaryRequest:
    sections: tuple[SummarySection, ...]
    sent_texts: tuple[bytes, ...]
    request: bytes
    cut: tuple[str, ...] = ()

    @property
    def hash(self):
        return sha256(self.request).hexdigest()

    @property
    def source_characters(self) -> int:
        return sum(len(section.member.chunk.source.decode("utf-8")) for section in self.sections)

    def report(self):
        return {"members": [section.member.place.address for section in self.sections],
                "characters": len(self.request.decode("utf-8")), "requestHash": self.hash,
                "cut": list(self.cut)}


def plan_summary_requests(sections: tuple[SummarySection, ...], prompts: SummaryPrompts) -> tuple[SummaryRequest, ...]:
    if not isinstance(prompts, SummaryPrompts) or type(sections) is not tuple or any(not isinstance(s, SummarySection) for s in sections):
        raise MycelError("invalid_input", "The summary request inputs are invalid.")
    identities = [s.member.chunk.identifier for s in sections]
    if (len(set(identities)) != len(identities)
            or len({s.member.place.address for s in sections}) != len(sections)
            or len({s.member.place.repository for s in sections}) > 1):
        raise MycelError("invalid_input", "The summary group has duplicate members or multiple repositories.")
    ordered = tuple(sorted(sections, key=lambda section: section.order))

    def render(group, texts):
        return prompts.render(SEPARATOR.join(section.place_line + "\n" + text.decode("utf-8") for section, text in zip(group, texts)))

    def divide(group):
        if not group:
            return ()
        texts = tuple(section.member.chunk.source for section in group)
        request = render(group, texts)
        if len(request) <= REQUEST_LIMIT:
            return (SummaryRequest(group, texts, request.encode("utf-8")),)
        if len(group) > 1:
            midpoint = len(group) // 2
            return divide(group[:midpoint]) + divide(group[midpoint:])
        suffix = "\n\n" + CUT_NOTICE
        prefix_budget = REQUEST_LIMIT - len(render(group, (b"",))) - len(suffix)
        if prefix_budget < 1:
            _settings()
        retained = texts[0].decode("utf-8")[:prefix_budget] + suffix
        sent = (retained.encode("utf-8"),)
        request = render(group, sent).encode("utf-8")
        return (SummaryRequest(group, sent, request, (group[0].member.place.address,)),)

    return divide(ordered)
