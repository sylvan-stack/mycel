"""Internal command declarations used by dispatch and the guide gate.

Feature tasks add handlers and their options together with their passing proofs.
Reserved commands cannot return a fabricated successful feature reply.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    name: str
    description: str
    scope: bool = True
    all_repositories: bool = False
    raw_arguments: bool = False
    extra_options: tuple[str, ...] = ()


COMMANDS = (
    CommandSpec("search", "Search by meaning or exact wording", extra_options=("--k <count>", "--only code|docs", "--no-fresh")),
    CommandSpec("ingest", "Bring repository knowledge up to date", all_repositories=True,
                extra_options=("--embed", "--confirm-empty")),
    CommandSpec("embed", "Embed pending chunk text", all_repositories=True, extra_options=("--dry-run", "--retry-failed")),
    CommandSpec("status", "Report repository counts", all_repositories=True),
    CommandSpec("repos", "List repositories or remove indexed rows", scope=False),
    CommandSpec("stale", "Report stale chunks"),
    CommandSpec("refs", "Report retained source references and faults", extra_options=("--unresolved",)),
    CommandSpec("derive", "Assert a dependency", scope=False, extra_options=("--remove",)),
    CommandSpec("confirm", "Record verification", scope=False, extra_options=("--by <name>", "--how read|check")),
    CommandSpec("justify", "State an Origin Link and record verification", scope=False,
                extra_options=("--by <name>", "--file <pairs.jsonl>")),
    CommandSpec("origins", "Report Origin Links and coverage", extra_options=("--missing", "--path <path>",
                "--changes", "--unresting", "--no-fresh", "--needs-nothing <requirement>",
                "--reason <text>", "--clear-needs-nothing <requirement>")),
    CommandSpec("drifts", "Report dependency review work", extra_options=("--closed", "--all-versions")),
    CommandSpec("relate", "Assert a relation", scope=False, extra_options=("--remove",)),
    CommandSpec("verifications", "Report verification records", extra_options=("--history",)),
    CommandSpec("classify", "Explicitly classify dependency review work", all_repositories=True,
                extra_options=("--k <count>", "--dry-run")),
    CommandSpec("summaries", "Report, build, regenerate or remove summaries", extra_options=("--dry-run",)),
    CommandSpec("overview", "Read the stored code overview", extra_options=("--dir <directory>",)),
    CommandSpec("grep", "Run grep with a related search tail", scope=False, raw_arguments=True),
    CommandSpec("read", "Read one exact chunk", extra_options=("--id <id>", "--context <lines>", "--no-fresh")),
    CommandSpec("undocumented", "List code that no document section describes", extra_options=("--path <path>", "--no-fresh")),
    CommandSpec("activity", "Report recorded work", all_repositories=True,
                extra_options=("--entry <id>", "--kind <kind>", "--k <count>")),
    CommandSpec("evaluate", "Explicitly evaluate retrieval or dependency review", extra_options=("--kind retrieval|drift", "--live")),
    CommandSpec("init", "Initialize the private index store", scope=False),
    CommandSpec("api-key", "Store a Voyage or Jev API key in the login Keychain", scope=False,
                extra_options=("voyage|jev",)),
    CommandSpec("info", "Report program and configuration diagnostics", scope=False),
)

BY_NAME = {spec.name: spec for spec in COMMANDS}


def help_reply(command: str | None = None) -> dict:
    selected = COMMANDS if command is None else (BY_NAME[command],)
    return {
        "program": "mycel",
        "version": "2.0.0",
        "usage": "mycel <command> [arguments]",
        "commands": [
            {"name": s.name, "description": s.description, "available": s.name in {"origins", "justify", "api-key", "info", "grep", "repos", "init", "refs", "derive", "relate", "confirm", "verifications", "ingest", "activity", "embed", "evaluate", "summaries", "read", "search", "undocumented", "overview", "classify", "drifts", "stale", "status"},
             "rawArguments": s.raw_arguments,
             "options": ([] if s.raw_arguments else
                         ["-h", "--help"] + (["--repo <name>"] if s.scope else []) +
                         (["--all"] if s.all_repositories else []) + list(s.extra_options))}
            for s in selected
        ],
        "options": ["-h", "--help", "--repo <name> (repeatable where supported)", "--all (where supported)"],
        "buildSelection": "Installed launcher: -v <number> must be first",
        "stage": "CLI foundation, strict settings and diagnostics, repository listing and atomic removal, complete repository status, complete scoped ingest, read-only ordered activity history and exact entry details, retained reference reporting, guarded dependency and relation assertions, exact verification and read-only history, atomic stated justification and on-demand Origin Coverage, exact indexed chunk reading, evidence-bearing search, scoped embedding, atomic summary builds, summary regeneration and removal, read-only summary status and dry-runs, finite classification, local provenance reports, and private store initialization; system grep preserves its output and can append a read-only related search tail",
    }
