"""Check a Beat implementation plan without writing to disk or the Index Store (MYC-20.13)."""

from dataclasses import dataclass, field
from pathlib import Path
import re

from ._cli import Invocation, Result, invocation_store
from ._errors import ErrorCode, MycelError
from ._locks import read_snapshot
from ._markdown import outline_markdown
from ._scope import RepositoryLocations
from ._source_refs import SourceAddressError, parse_source_address


_STEP_LIKE = re.compile(r"^[ \t]*(?:[-*+][ \t]+|\[[^\]]*\][ \t]+|[0-9]+(?:\.[0-9]+)*[.)](?=[ \t]|$))")
_NUMBERED = re.compile(
    r"^(?P<indent>[ \t]*)(?:(?P<bullet>[-*+])[ \t]+)?"
    r"(?:\[(?P<check>[^\]]*)\][ \t]+)?"
    r"(?P<number>[0-9]+(?:\.[0-9]+)*)[.)]?(?=[ \t]|$)[ \t]*(?P<text>.*)$"
)
_EXCEPTION = re.compile(r"No plan:[ \t]+\S.*")


@dataclass
class Step:
    number: str
    done: bool
    line: int
    lines: list[str]
    problems: list[dict] = field(default_factory=list)

    def problem(self, kind: str, detail: str) -> None:
        self.problems.append(_problem(self.number, kind, detail))


def _problem(step: str | None, kind: str, detail: str) -> dict:
    return {"step": step, "kind": kind, "detail": detail}


def _plan_tree(lines: tuple[str, ...], first_line: int) -> tuple[list[Step], list[tuple[int, dict]]]:
    steps: list[Step] = []
    problems: list[tuple[int, dict]] = []
    position: list[int] = []
    continuation: Step | None = None
    for number, line in enumerate(lines, first_line):
        if not line.strip():
            continue
        if not _STEP_LIKE.match(line):
            if line.strip().startswith("No plan:"):
                problems.append((number, _problem(None, "form", "The plan exception needs a reason and must be its sole line.")))
                continuation = None
            elif continuation is not None and line.startswith((" ", "\t")):
                continuation.lines.append(line.strip())
            else:
                # Review verdicts and amendments may follow the steps.
                continuation = None
            continue

        match = _NUMBERED.fullmatch(line.rstrip())
        if match is None:
            problems.append((number, _problem(None, "form", f"Line {number} has a step without a number.")))
            continuation = None
            continue
        step = Step(match["number"], match["check"] in ("x", "X"), number, [match["text"]])
        steps.append(step)
        continuation = step
        if match["bullet"] not in ("-", "*") or match["check"] not in (" ", "x", "X"):
            step.problem("form", "Use a checkbox list item for each step.")
        if not match["text"]:
            step.problem("form", "The step needs text.")
        indent = match["indent"]
        depth, remainder = divmod(len(indent), 2)
        if remainder or "\t" in indent:
            step.problem("form", "Use two spaces per nesting level.")
        if depth > len(position):
            step.problem("form", "A sub-step needs a parent step.")
            continue
        if depth == len(position):
            position.append(1)
        else:
            del position[depth + 1:]
            position[depth] += 1
        expected = ".".join(map(str, position))
        if step.number != expected:
            step.problem("form", f"Expected step {expected} at this position.")

    if not steps and not problems:
        problems.append((first_line, _problem(None, "form", "The Plan section has no numbered steps.")))
    return steps, problems


def _read_plan(text: str, fallback: str) -> tuple[str, list[Step], list[tuple[int, dict]]]:
    outline = outline_markdown(text)
    title = next((heading.title for heading in outline.headings if heading.level == 1), "")
    beat = title.partition(" · ")[0] or fallback
    plans = [heading for heading in outline.headings if heading.level == 2 and heading.title == "Plan"]
    if not plans:
        return beat, [], [(0, _problem(None, "form", "The Beat has no Plan section."))]
    problems = [] if len(plans) == 1 else [(0, _problem(None, "form", "The Beat has more than one Plan section."))]
    all_steps: list[Step] = []
    for plan in plans:
        end = next((heading.line - 1 for heading in outline.headings
                    if heading.line > plan.line and heading.level <= 2), len(outline.lines))
        lines = outline.lines[plan.last_line:end]
        content = [line.strip() for line in lines if line.strip()]
        if len(content) == 1 and _EXCEPTION.fullmatch(content[0]):
            continue
        steps, faults = _plan_tree(lines, plan.last_line + 1)
        all_steps.extend(steps)
        problems.extend(faults)
    return beat, all_steps, problems


_REPO_PREFIX = r"[A-Za-z0-9_][A-Za-z0-9_.-]*:"
_PATH_TOKEN = re.compile(r"`([^`]+)`|(?<![\w.:-])(" + _REPO_PREFIX + r"[^\s,;)`]+)")
_REPO_PATH = re.compile(_REPO_PREFIX)
_FILE_FIELD = re.compile(r"\bFiles:[ \t]*(.*?)(?=\s+(?:Serves|Produces)\b|$)")


def _path_names(text: str, *, file_field: bool):
    for match in _PATH_TOKEN.finditer(text):
        value = match[1] or match[2].rstrip(".;")
        if not (repo := _REPO_PATH.match(value)):
            continue
        path = value[repo.end():]
        if path.startswith("//"):
            continue
        if file_field or "/" in path or "." in path:
            yield value


def _named_files(step: Step) -> tuple[str, ...]:
    text = " ".join(step.lines)
    fields = _FILE_FIELD.findall(text)
    paths = (path for field in fields for path in _path_names(field, file_field=True)) if fields else (
        _path_names(text, file_field=False)
    )
    return tuple(dict.fromkeys(paths))


def _file_problem(spelling: str, locations: RepositoryLocations) -> str | None:
    folder = spelling.endswith("/")
    try:
        address = parse_source_address(spelling.removesuffix("/"))
    except SourceAddressError:
        return "Use a repository name and a relative code path."
    if address.root not in (None, "code") or address.name is not None:
        return "Use a code path without a chunk selector."
    try:
        matches = locations.named(address.repository)
    except MycelError:
        return "No configured code checkout has this repository name."
    if len(matches) != 1 or matches[0].name != address.repository:
        return "No configured code checkout has this repository name."
    repository = matches[0].at(locations.cwd)
    if repository.fault or repository.code is None:
        return "The configured code checkout could not be resolved."
    try:
        root = repository.code.path.resolve()
        path = (root / Path(address.path)).resolve()
        if not path.is_relative_to(root):
            return "The path resolves outside its configured code checkout."
        if path.exists():
            return "The path is a file, but a folder was named." if folder and not path.is_dir() else None
        if not path.parent.is_dir():
            return "Neither the path nor its containing folder exists."
    except (OSError, RuntimeError, ValueError):
        return "The path could not be resolved in its configured code checkout."
    return None


def _check_files(steps: list[Step], locations: RepositoryLocations) -> None:
    for step in steps:
        for spelling in _named_files(step):
            if problem := _file_problem(spelling, locations):
                step.problem("file", f"{spelling}: {problem}")


_ORIGIN_ID = re.compile(
    r"(?<![\w./-])[A-Z][A-Z0-9]*-(?:D[0-9]+|[0-9]+\.[0-9]+)"
    r"(?![\w/-]|\.[A-Za-z0-9])"
)


def _origin_names(step: Step) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_ORIGIN_ID.findall(" ".join(step.lines))))


def _resolved_origin_names(connection, names: list[str]) -> set[str]:
    with read_snapshot(connection):
        rows = connection.execute("""
            SELECT DISTINCT l.metadata->>'name'
            FROM public.mycel_locations l
            JOIN public.mycel_chunk_versions v ON v.id = l.chunk_version
            JOIN public.mycel_chunks c ON c.id = v.chunk_id
            WHERE c.kind IN ('req', 'dec')
              AND l.kind = 'disk' AND l.file_location IS NOT NULL
              AND l.metadata->>'name' = ANY(%s)
        """, (names,)).fetchall()
    return {name for (name,) in rows}


def _check_origins(invocation: Invocation, steps: list[Step]) -> None:
    named = [(step, _origin_names(step)) for step in steps]
    names = sorted({name for _, ids in named for name in ids})
    if not names:
        return
    with invocation_store(invocation) as (connection, _):
        resolved = _resolved_origin_names(connection, names)
    for step, ids in named:
        for name in ids:
            if name not in resolved:
                step.problem("origin", f"{name} does not resolve to an indexed requirement or decision.")


def handle_plan_check(invocation: Invocation) -> Result:
    if invocation.settings is None:
        raise MycelError(ErrorCode.INTERNAL, "Settings were not loaded for this invocation.")
    _, spelling = invocation.arguments
    try:
        path = Path(spelling).expanduser()
        if not path.is_file():
            raise OSError()
        source = path.read_text(encoding="utf-8")
    except (OSError, RuntimeError, UnicodeError, ValueError):
        raise MycelError(ErrorCode.IO, "The Beat file could not be read as UTF-8 text.") from None

    beat, steps, problems = _read_plan(source, path.stem)
    _check_files(steps, RepositoryLocations(invocation.settings))
    _check_origins(invocation, steps)
    problems.extend((step.line, problem) for step in steps for problem in step.problems)
    return Result({
        "beat": beat,
        "steps": [{"number": step.number, "done": step.done} for step in steps],
        "problems": [problem for _, problem in sorted(problems, key=lambda item: item[0])],
    })
