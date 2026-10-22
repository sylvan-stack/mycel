#!/usr/bin/env python3
"""Audit the Hub's documented Mycel commands against installed JSON help.

Only --help is executed. Markdown examples are read as text, never as shell
commands. Grep arguments belong to the PATH-selected grep and are listed as
delegated rather than compared with Mycel options.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys


FILES = (
    "README.md", "tools/mycel.md", "operations/OVERVIEW.md",
    "operations/code-research-levels.md", "operations/code-research.md",
    "operations/deep-research.md", "operations/retrieval.md",
    "operations/embedding.md", "operations/authored-work-integration.md",
)
SPANS = re.compile(r"```[^\n]*\n(?P<fence>.*?)```|`(?P<inline>[^`]+)`", re.S)
PROGRAM = re.compile(r"(?<![\w./-])mycel(?=\s|$)")
OPTION = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*|-[A-Za-z])(?![\w-])")


@dataclass(frozen=True)
class Mention:
    line: int
    command: str
    options: tuple[str, ...]


def mentions(text: str) -> list[Mention]:
    result = []
    for span in SPANS.finditer(text):
        group = "fence" if span["fence"] is not None else "inline"
        body = span[group]
        start = span.start(group)
        if group == "inline" and body.strip().startswith("--"):
            options = tuple(dict.fromkeys(OPTION.findall(body)))
            if options:
                result.append(Mention(text.count("\n", 0, start) + 1,
                                      "<option>", options))
            continue
        # A continued shell example is one invocation; keep line counts exact.
        if group == "inline":
            lines = [(0, body.replace("\n", " "))]
        else:
            lines, offset, pending, pending_start = [], 0, "", 0
            for line in span[group].splitlines(keepends=True):
                if not pending:
                    pending_start = offset
                pending += line.rstrip("\n").removesuffix("\\") + " "
                if not line.rstrip("\n").endswith("\\"):
                    lines.append((pending_start, pending))
                    pending = ""
                offset += len(line)
            if pending:
                lines.append((pending_start, pending))
        for offset, line in lines:
            found = PROGRAM.search(line)
            if not found:
                continue
            sample = line[found.end():].strip()
            lex = shlex.shlex(sample, posix=False)
            lex.whitespace_split = True
            try:
                words = list(lex)
            except ValueError as error:
                raise ValueError("unclosed quote in documented Mycel command") from error
            if not words or not re.fullmatch(r"[a-z][a-z0-9-]*|--[a-z][a-z0-9-]*|-[A-Za-z]", words[0]):
                continue
            options = tuple(dict.fromkeys(
                match[0] for word in words if not word.startswith(("'", '"'))
                for match in OPTION.finditer(word)))
            result.append(Mention(text.count("\n", 0, start + offset) + 1,
                                  words[0], options))
    return result


def audit(text: str, help_document: dict) -> list[tuple[Mention, tuple[str, ...]]]:
    commands = {item["name"]: item for item in help_document["commands"]}
    root_options = {match[0] for value in help_document["options"]
                    for match in OPTION.finditer(value)}
    all_options = root_options | {match[0] for command in commands.values()
                                 for value in command["options"]
                                 for match in OPTION.finditer(value)}
    rows = []
    for mention in mentions(text):
        if mention.command == "<option>":
            allowed, faults = all_options, []
        elif mention.command in ("--help", "-h"):
            allowed, faults = root_options, []
        elif mention.command not in commands:
            rows.append((mention, ("unknown command",)))
            continue
        else:
            command = commands[mention.command]
            if command.get("available") is not True:
                rows.append((mention, ("command is unavailable",)))
                continue
            if command.get("rawArguments"):
                rows.append((mention, ()))
                continue
            allowed = {match[0] for value in command["options"]
                       for match in OPTION.finditer(value)}
            faults = []
        faults.extend(f"unknown option {option}" for option in mention.options
                      if option not in allowed)
        rows.append((mention, tuple(faults)))
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--program", default="mycel")
    arguments = parser.parse_args(argv)
    try:
        process = subprocess.run([arguments.program, "--help"], capture_output=True,
                                 text=True, timeout=30, check=True)
        help_document = json.loads(process.stdout)
        if help_document.get("program") != "mycel":
            raise ValueError("help is not for Mycel")
        failed, count, standalone = False, 0, 0
        for name in FILES:
            text = (arguments.corpus / name).read_text(encoding="utf-8")
            for mention, faults in audit(text, help_document):
                if mention.command == "<option>":
                    standalone += 1
                else:
                    count += 1
                options = " ".join(mention.options)
                state = "; ".join(faults) if faults else (
                    "grep arguments delegated" if mention.command == "grep" else "OK")
                label = "Mycel option" if mention.command == "<option>" else f"mycel {mention.command}"
                print(f"{name}:{mention.line}: {label} {options}: {state}")
                failed |= bool(faults)
        print(f"{count} command mentions and {standalone} standalone option mentions "
              f"in {len(FILES)} files; "
              + ("unsupported commands/options found" if failed else "all supported"))
        return int(failed)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"Command audit failed: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
