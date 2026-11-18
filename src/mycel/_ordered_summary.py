"""Private source-ordered Artifact exports with optional Narrator overviews."""

from dataclasses import dataclass
from hashlib import sha256
from itertools import batched
import os
from pathlib import Path
import stat

from ._errors import MycelError
from ._evidence import EvidenceError
from ._markdown import split_markdown
from ._safeguards import InvocationPolicy, require_model_call
from ._summary_browser import summary_browser_output, write_summary_browser
from ._summary_labels import SummaryLabels
from ._summary_request import REQUEST_LIMIT, SEPARATOR, summary_command, summary_configuration_guard
from ._summary_writer import SummaryWriter


_LEAF_CHARACTERS = 2_000
_CHILDREN = 4
_MARKDOWN = {".md", ".markdown", ".mdown", ".mdx"}


@dataclass(slots=True)
class _Node:
    label: str
    first: int
    last: int
    has_body: bool
    source: str | None = None
    children: tuple["_Node", ...] = ()
    summary: str | None = None

    def browser_data(self):
        if self.source is not None:
            return {"label": self.label, "source": self.source}
        return {"label": self.label, "summary": self.summary,
                "children": [child.browser_data() for child in self.children]}


def ordered_arguments(arguments, *, has_scope):
    filename = arguments[-1] if len(arguments) >= 4 else None
    paths = arguments[1:-2]
    if (has_scope or len(arguments) < 4 or arguments[-2] != "--output"
            or not isinstance(filename, str) or not filename.strip() or "\0" in filename
            or any(not isinstance(path, str) or not path or "\0" in path for path in paths)):
        raise MycelError("invalid_input", "Use summaries ordered <artifact> [<artifact> ...] --output <file>.")
    return paths, filename


def _capture(argument):
    path = Path(argument)
    try:
        path = path.expanduser()
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise MycelError("invalid_input", f"Artifact must be a regular file: {argument}")
            data = stream.read()
            after = os.fstat(stream.fileno())
    except (OSError, RuntimeError, UnicodeError):
        raise MycelError("io", f"Could not read Artifact: {argument}") from None
    if len(data) != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise MycelError("busy", f"Artifact changed during capture: {argument}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise MycelError("invalid_input", f"Artifact must contain UTF-8 text: {argument}") from None
    return path, text, sha256(data).hexdigest()


def _sections(path, text):
    if path.suffix.lower() not in _MARKDOWN:
        yield text, 0, None
        return
    raw = text.encode("utf-8")
    end = 0
    for chunk in split_markdown(raw).chunks:
        start = chunk.span.byte_start
        if end < start:
            gap = raw[end:start].decode("utf-8")
            yield gap, len(gap), "Preamble"
        yield chunk.text, len(chunk.text) - len(chunk.body), chunk.title
        end = chunk.span.byte_end
    if end < len(raw):
        gap = raw[end:].decode("utf-8")
        yield gap, len(gap), None


def _leaves(path, text):
    leaves = []
    for section, body_start, title in _sections(path, text):
        start = 0
        while start < len(section):
            end = min(start + _LEAF_CHARACTERS, len(section))
            if end < len(section):
                newline = section.rfind("\n", start + _LEAF_CHARACTERS // 2, end)
                if newline != -1:
                    end = newline + 1
                elif section[end - 1:end + 1] == "\r\n":
                    end -= 1
            number = len(leaves) + 1
            label = title if title and start == 0 else f"Part {number}"
            leaves.append(_Node(label, number, number, bool(section[max(start, body_start):end].strip()),
                                source=section[start:end]))
            start = end
    return tuple(leaves) or (_Node("Source", 1, 1, False, source=""),)


def _tree(path, text):
    row = _leaves(path, text)
    levels = []
    while len(row) > 1 or not levels:
        parents = []
        level = []
        for group in batched(row, _CHILDREN):
            if len(group) == 1 and len(row) > 1:
                parents.append(group[0])
                continue
            first, last = group[0].first, group[-1].last
            label = f"Parts {first}–{last}" if first != last else "Overview"
            parent = _Node(label, first, last, any(child.has_body for child in group), children=group)
            level.append(parent)
            parents.append(parent)
        levels.append(level)
        row = tuple(parents)
    return row[0], levels


def _generate(levels, settings, program):
    guard = summary_configuration_guard(settings, "ordered", program)
    writer = SummaryWriter(program.argv, settings.values["summaries"]["at_once"], before_launch=guard)
    labels = SummaryLabels(settings, program, guard)
    for level in levels:
        targets, requests, lengths = [], [], []
        for node in level:
            texts = [child.source if child.source is not None else child.summary
                     for child in node.children if child.has_body]
            if not texts or any(text is None for text in texts):
                continue
            length = sum(map(len, texts))
            if length > _CHILDREN * _LEAF_CHARACTERS:
                continue
            sections = SEPARATOR.join(f"Artifact › Part {index}\n{text}" for index, text in enumerate(texts, 1))
            request = program.prompts.render(sections)
            if len(request) <= REQUEST_LIMIT:
                targets.append(node)
                requests.append(request.encode("utf-8"))
                lengths.append(length)
        completed, responses = [], []
        for node, result in zip(targets, writer.write_many(tuple(requests), source_characters=tuple(lengths)),
                                strict=True):
            if result.response is not None:
                node.summary = result.response.decode("utf-8")
                completed.append(node)
                responses.append(result.response)
        for node, label in zip(completed, labels.write_many(tuple(responses)), strict=True):
            if label is not None:
                node.label = label
    guard()


def export_ordered_summaries(invocation):
    from ._cli import Result

    paths, filename = ordered_arguments(invocation.arguments,
        has_scope=bool(invocation.repositories) or invocation.all_repositories)
    output = summary_browser_output(filename)
    captured = tuple(_capture(path) for path in paths)
    settings = invocation.settings
    trees, reports = [], []
    program = None
    configured = bool(settings.values["summaries"].get("model_command"))
    if configured:
        require_model_call(InvocationPolicy("summaries", action="ordered"), "summary")
        try:
            program = summary_command(settings, operation="ordered")
        except MycelError as error:
            if error.code != "settings":
                raise
    adapter_available = program is not None
    for path, text, digest in captured:
        root, levels = _tree(path, text)
        if program is not None:
            try:
                _generate(levels, settings, program)
            except EvidenceError as error:
                if error.status != "inputs_changed":
                    raise
                program = None
        summaries = sum(node.summary is not None for level in levels for node in level)
        unavailable = sum(map(len, levels)) - summaries
        trees.append({"artifact": str(path), "sha256": digest, "root": root.browser_data()})
        reports.append({"artifact": str(path), "sha256": digest, "summaries": summaries, "unavailable": unavailable})
    write_summary_browser(output, trees, template_name="ordered-summary.html")
    return Result({"output": str(output), "adapterConfigured": configured,
                   "adapterAvailable": adapter_available, "artifacts": reports})
