"""Read the numbered checkbox tree of a Beat's implementation plan (MYC-20.13)."""

from dataclasses import dataclass, field
import re

from ._markdown import outline_markdown


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
