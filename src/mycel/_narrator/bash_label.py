"""Derive a short activity label from shell text without interpreting it as code."""

import re
import shlex

MAX_COMMAND_CHARS = 8192
FALLBACK = "Run shell command"
SHELL_NAMES = frozenset({"bash", "shell", "exec_command"})
_OPERATORS = frozenset("|&;()<>\n")
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z_0-9]*=")
_SOURCE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,40}\.(?:md|py|svelte|[cm]?[jt]s[x]?|json|ya?ml|toml|sql|css|sh)\Z")
_FILE_COMMANDS = {
    "cat": ("Read", "Read files"),
    "sed": ("Inspect", "Inspect text"),
    "head": ("Read", "Read file starts"),
    "tail": ("Read", "Read file ends"),
    "wc": ("Count lines in", "Count file contents"),
    "rg": ("Search", "Search files"),
    "grep": ("Search", "Search files"),
}
_GIT = {
    "diff": "Review Git changes", "status": "Check Git status", "log": "Inspect Git history",
    "show": "Inspect a Git revision", "rev-parse": "Resolve a Git revision", "add": "Stage Git changes",
    "commit": "Commit Git changes", "push": "Push Git changes", "fetch": "Fetch Git updates",
}
_SIMPLE = {
    "ls": "List directory contents", "find": "Find files", "pwd": "Check the working directory",
    "cd": "Change directory", "git": "Run Git command", "which": "Locate a command",
    "python": "Run Python", "python3": "Run Python", "node": "Run JavaScript",
    "npm": "Run npm command", "pnpm": "Run pnpm command", "uv": "Run Python tooling",
    "curl": "Fetch a network resource", "mkdir": "Create directories", "cp": "Copy files",
    "mv": "Move files", "rm": "Remove files", "chmod": "Change file permissions",
    "echo": "Print text", "printf": "Print text", "jq": "Process JSON", "sort": "Sort lines",
}


def _basename(word: str) -> str:
    return word.rstrip("/").rsplit("/", 1)[-1]


def _action(name: str, arguments: list[str]) -> str:
    if name in _FILE_COMMANDS:
        verb, fallback = _FILE_COMMANDS[name]
        source = next((_basename(arg) for arg in arguments if _SOURCE.fullmatch(_basename(arg))), None)
        return f"{verb} {source}" if source else fallback
    if name == "git":
        skip = False
        for arg in arguments:
            if skip:
                skip = False
            elif arg in ("-C", "-c", "--git-dir", "--work-tree"):
                skip = True
            elif not arg.startswith("-"):
                return _GIT.get(arg, _SIMPLE[name])
    return _SIMPLE.get(name, FALLBACK)


def label_bash(command: str) -> str:
    """Label the first substantive shell activity using only static tokens."""
    if not command or "\0" in command or len(command) > MAX_COMMAND_CHARS:
        return FALLBACK
    lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;()<>\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return FALLBACK

    segments: list[list[str]] = [[]]
    for word in words:
        if word and all(character in _OPERATORS for character in word):
            if "<" in word or ">" in word:
                break  # A redirect target isn't a command or a subject of the action.
            segments.append([])
        elif word and (segments[-1] or not _ASSIGNMENT.match(word)):
            segments[-1].append(word)

    first: str | None = None
    for segment in segments:
        if not segment:
            continue
        name, *arguments = segment
        name = _basename(name)
        action = _action(name, arguments)
        if first is None:
            first = action
        if name not in {"cd", "echo", "printf"}:
            return action
    return first or FALLBACK


def shell_tool_label(name: object, input_value: object) -> str | None:
    if not isinstance(name, str) or name.casefold() not in SHELL_NAMES:
        return None
    command = input_value.get("command") if isinstance(input_value, dict) else input_value
    return label_bash(command) if isinstance(command, str) and not command.startswith(("{", "[")) else FALLBACK
