"""Complete, deterministic summary requests for the configured text writer.

Planning is offline. Publication, grouping and summary command replies belong
to their respective consumers; no request here makes searchable summary rows.
"""

from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files
import json
from pathlib import Path

from ._embedding_plan import document_place_line
from ._errors import MycelError
from ._resolver import SelectionMember, _validate_chunk
from ._settings import SettingsSnapshot
from ._source_refs import SourceAddress


REQUEST_LIMIT = 48_000
CUT_NOTICE = "[Mycel: source text cut at request limit]"
SEPARATOR = "\n\n---\n\n"


def _settings():
    raise MycelError("settings", "The summary command or instruction/task framing is invalid or unavailable.")


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


def load_summary_prompts(settings: SettingsSnapshot) -> SummaryPrompts:
    settings.require_valid(require_store=False)
    folder = settings.values["summaries"].get("instructions")
    try:
        if folder is not None:
            root = Path(folder)
            return SummaryPrompts((root / "raptor-summary.md").read_bytes(),
                                  (root / "raptor-request.md.tmpl").read_bytes(), "override")
        data = json.loads(files("mycel").joinpath("data/summary-prompts.json").read_bytes())
        if data["schema_version"] != 1:
            _settings()
        return SummaryPrompts(data["instruction"].encode("utf-8"), data["task"].encode("utf-8"), data["profile"])
    except (OSError, ValueError, KeyError, TypeError):
        _settings()


def summary_command(settings: SettingsSnapshot, *, operation: str, dry_run: bool = False) -> tuple[str, ...] | None:
    """Apply the generation-only writer requirement before any requests."""
    settings.require_valid(require_store=False)
    if operation not in {"build", "regenerate", "status", "remove", "search"} or type(dry_run) is not bool:
        raise MycelError("invalid_input", "The summary operation is invalid.")
    if operation not in {"build", "regenerate"} or dry_run:
        return None
    command = settings.values["summaries"].get("command")
    if (not isinstance(command, tuple) or not command
            or any(not isinstance(arg, str) or "\0" in arg for arg in command)
            or not command[0].strip()):
        _settings()
    load_summary_prompts(settings)
    return command


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
