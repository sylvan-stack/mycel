"""Ingest real repositories into a throwaway store, twice, while a file changes.

The check any Beat can run (SYL-232). It works on copies of the `readonly`
clones of the repositories it names and of their corpora, writes only to a database
of its own named `mycel_check_real_<id>` on the configured check server, and
drops it at the end. During the first pass of the last repository a helper
changes one Markdown file of the corpus copy: the pass must still complete and
name the file under `changedDuringPass`, and the second pass must take it up
(MYC-1.37). Then it runs `search`, `read`, `refs`, `stale`, `status` and
`embed --dry-run` on the result. Every command must end with status 0, and no
reply may carry the error code `internal`.

Commands run from a private copy of the current package with fictional Build
1a. This exercises the numbered public activity path without registering,
installing or qualifying a Build. Each changing ingest must add exactly one
entry for its repository, with exact reply counts and readable file/identity
details; a no-op must leave its history unchanged.

    PYTHONPATH=src .venv/bin/python scripts/check_real.py --report /tmp/check_real.json

Options: `--store-settings` (default `~/.mycel/config.toml`, only its
`store.address` is read), `--clones` (default `~/repos/sylvan-stack/readonly`),
`--artifacts` (default `~/Artifacts`), `--repos` (default `arbol mycel`, in the
order they are ingested), `--passes` (default 2), `--no-change` to skip the
helper, `--keep` to keep the database and the copies, and `--report` for the
JSON record, which belongs outside every corpus and repository.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from uuid import uuid4

REPOSITORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY / "src"))

from mycel._check_store import NativePostgresBackend  # noqa: E402
from mycel._coverage import require_check_database  # noqa: E402

CHANGED_FILE = "INDEX.md"
TEST_BUILD = 26
COMMANDS = (
    ("search", "--repo", "{last}", "the pass publishes the capture it read"),
    ("read", "--repo", "mycel", "mycel:@code/src/mycel/_ingest.py#ingest"),
    ("refs", "--repo", "{last}"),
    ("stale", "--repo", "{last}"),
    ("status", "--all"),
    ("embed", "--dry-run", "--repo", "{last}"),
)


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _settings(address: str, repositories: dict[str, tuple[Path, Path]]) -> str:
    lines = ["[store]", f"address = {_toml_string(address)}", ""]
    for name, (code, artifact) in repositories.items():
        lines += [f"[repos.{json.dumps(name)}]", "enabled = true", "code_subdirs = []",
                  f"code_root = {_toml_string(str(code))}", f"artifact_root = {_toml_string(str(artifact))}", ""]
    return "\n".join(lines)


def _copy(source: Path, target: Path) -> None:
    """Copy a corpus with its git store; APFS clones make this instant."""
    try:
        subprocess.run(["/bin/cp", "-Rc", str(source), str(target)], check=True, capture_output=True)
    except (subprocess.CalledProcessError, OSError):
        shutil.copytree(source, target, symlinks=True)


def _remove(folder: Path) -> None:
    """Remove the copies, read-only files of a corpus included."""
    def writable(function, path, _):
        os.chmod(os.path.dirname(path), 0o700)
        os.chmod(path, 0o600)
        function(path)
    shutil.rmtree(folder, onexc=writable)
    if folder.exists():
        for root, folders, files in os.walk(folder):
            for name in folders + files:
                os.chmod(os.path.join(root, name), 0o700)
        shutil.rmtree(folder, ignore_errors=True)


def _numbered_package(work: Path) -> Path:
    """Use an explicit test identity; never invent an installed Build record."""
    root = work / "numbered-test-package"
    package = root / "mycel"
    shutil.copytree(REPOSITORY / "src/mycel", package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (package / "data/development-identity.json").unlink(missing_ok=True)
    (package / "data/build-identity.json").write_text(
        json.dumps({"schemaVersion": 1, "build": TEST_BUILD}) + "\n", encoding="utf-8")
    return root


def _mycel(settings: Path, *arguments: str, package: Path) -> tuple[int, dict | None, float]:
    started = time.monotonic()
    completed = subprocess.run([sys.executable, "-B", "-P", "-m", "mycel", *arguments],
                               env={**os.environ, "MYCEL_CONFIG": str(settings),
                                    "PYTHONPATH": str(package)},
                               cwd=settings.parent, capture_output=True, text=True)
    elapsed = time.monotonic() - started
    try:
        reply = json.loads(completed.stdout) if completed.stdout.strip() else None
    except json.JSONDecodeError:
        reply = {"unparsed": completed.stdout[-2000:]}
    if completed.stderr.strip():
        reply = {"reply": reply, "stderr": completed.stderr[-2000:]}
    return completed.returncode, reply, elapsed


def _internal(value) -> bool:
    if isinstance(value, dict):
        if value.get("code") == "internal":
            return True
        return any(_internal(item) for item in value.values())
    if isinstance(value, list):
        return any(_internal(item) for item in value)
    return False


def _entries(reply) -> list[dict] | None:
    entries = reply.get("entries") if isinstance(reply, dict) else None
    if not isinstance(entries, list) or not all(
            isinstance(entry, dict) and isinstance(entry.get("id"), str) for entry in entries):
        return None
    if len({entry["id"] for entry in entries}) != len(entries):
        return None
    return entries


def _activity_problems(repository: str, result: dict, before, after, detail) -> list[str]:
    """Check public history against this invocation, not an older good entry."""
    previous, current = _entries(before), _entries(after)
    if previous is None or current is None:
        return ["activity history is malformed"]
    if not isinstance(result.get("changed"), bool):
        return ["ingest reply has no change result"]
    if not result["changed"]:
        return [] if previous == current else ["a no-op changed activity history"]
    old = {entry["id"]: entry for entry in previous}
    new = [entry for entry in current if entry["id"] not in old]
    if len(new) != 1:
        return [f"a changing ingest added {len(new)} entries instead of one"]
    problems = []
    if any(entry != old[entry["id"]] for entry in current if entry["id"] in old):
        problems.append("ingest changed an earlier activity entry")
    entry = new[0]
    expected = {"repository": repository, "kind": "ingest", "startedBy": "command",
                "build": format(TEST_BUILD, "x"), "outcome": "done", "counts": result}
    for key, value in expected.items():
        if entry.get(key) != value:
            problems.append(f"activity {key} differs from the completed numbered ingest")
    details = _entries(detail)
    if details is None or len(details) != 1 or any(
            details[0].get(key) != value for key, value in entry.items()):
        problems.append("activity detail differs from its listed entry")
    elif not all(isinstance(details[0].get(key), list) for key in ("files", "decisions")):
        problems.append("activity detail has no file/identity lists")
    else:
        files, chunks = result.get("files", {}), result.get("chunks", {})
        if any(files.get(key, 0) for key in ("changed", "removed")) and not details[0]["files"]:
            problems.append("activity detail omits changed files")
        if any(chunks.get(key, 0) for key in ("new", "edited", "renamed", "removed")) and not details[0]["decisions"]:
            problems.append("activity detail omits identity decisions")
    return problems


class Helper(threading.Thread):
    """Change one Markdown file once the pass has begun to write."""

    def __init__(self, backend: NativePostgresBackend, database: str, path: Path):
        super().__init__(daemon=True)
        self.backend, self.database, self.path = backend, database, path
        self.changed_at = None
        self.waited = None
        self.stop = threading.Event()

    def run(self) -> None:
        started = time.monotonic()
        while not self.stop.is_set():
            with self.backend.connection(self.database) as connection:
                # Invocation registration writes before capture. Wait for the
                # publication's file-table lock, which is held until commit.
                writing = connection.execute(
                    "SELECT count(*) FROM pg_catalog.pg_locks l "
                    "JOIN pg_catalog.pg_stat_activity a ON a.pid=l.pid "
                    "WHERE a.datname=%s AND l.relation='public.mycel_files'::regclass "
                    "AND l.mode='RowExclusiveLock' AND l.granted", (self.database,)).fetchone()[0]
            if writing:
                self.path.write_bytes(self.path.read_bytes() + b"\nChanged by check_real.py during the first pass.\n")
                self.changed_at = time.time()
                self.waited = time.monotonic() - started
                return
            time.sleep(0.5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--store-settings", type=Path, default=Path("~/.mycel/config.toml"))
    parser.add_argument("--clones", type=Path, default=Path("~/repos/sylvan-stack/readonly"))
    parser.add_argument("--artifacts", type=Path, default=Path("~/Artifacts"))
    parser.add_argument("--repos", nargs="+", default=["arbol", "mycel"])
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--no-change", action="store_true")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args(argv)
    if arguments.passes < 1 or not arguments.repos:
        parser.error("at least one pass and one repository")

    owner = tomllib.loads(arguments.store_settings.expanduser().read_text(encoding="utf-8"))["store"]["address"]
    work = Path(tempfile.mkdtemp(prefix="mycel_check_real_"))
    os.chmod(work, 0o700)
    journal = work / "journal"
    journal.mkdir(mode=0o700)
    backend = NativePostgresBackend(owner, _ownership_journal=journal)
    database = require_check_database("mycel_check_real_" + uuid4().hex)
    report = {"database": database, "server": backend.server_label, "repositories": {},
              "commands": [], "ok": True, "problems": [],
              "runtime": {"kind": "numbered_test_package", "build": format(TEST_BUILD, "x"),
                          "qualifiedBuild": False}}
    last = arguments.repos[-1]

    def problem(text: str) -> None:
        report["ok"] = False
        report["problems"].append(text)
        print("problem:", text, file=sys.stderr)

    try:
        package = _numbered_package(work)

        def command(*words: str):
            return _mycel(settings, *words, package=package)

        def history(name: str):
            status, reply, _ = command("activity", "--repo", name, "--kind", "ingest", "--k", "500")
            if status != 0 or _internal(reply):
                problem(f"activity history for {name} failed with status {status}")
            return reply

        repositories = {}
        for name in arguments.repos:
            # Copies of the clone and the corpus: another agent's `git pull` of a
            # `readonly` clone during the run cannot change this check's inputs.
            code = work / "code" / name
            artifact = work / "artifacts" / name
            code.parent.mkdir(exist_ok=True)
            artifact.parent.mkdir(exist_ok=True)
            _copy(arguments.clones.expanduser() / name, code)
            _copy(arguments.artifacts.expanduser() / name, artifact)
            repositories[name] = (code, artifact)
        backend.create_database(database)
        settings = work / "settings.toml"
        settings.write_text(_settings(backend.address(database), repositories), encoding="utf-8")
        settings.chmod(0o600)
        os.environ["MYCEL_CONFIG"] = str(settings)  # the native initializer wants it selected
        backend.initialize(settings)
        print(f"store {database} on {backend.server_label}; copies under {work}", file=sys.stderr)

        changed_path = repositories[last][1] / CHANGED_FILE
        for number in range(1, arguments.passes + 1):
            for name in arguments.repos:
                before = history(name)
                helper = None
                if number == 1 and name == last and not arguments.no_change:
                    helper = Helper(backend, database, changed_path)
                    helper.start()
                status, reply, elapsed = command("ingest", "--repo", name)
                if helper is not None:
                    helper.stop.set()
                    helper.join(timeout=5)
                entry = {"pass": number, "status": status, "seconds": round(elapsed, 1), "reply": reply}
                if helper is not None:
                    entry["helper"] = {"changed": helper.changed_at is not None, "file": str(changed_path),
                                       "waitedSeconds": None if helper.waited is None else round(helper.waited, 1)}
                report["repositories"].setdefault(name, []).append(entry)
                repositories_reply = (reply or {}).get("repositories", {}) if isinstance(reply, dict) else {}
                if isinstance(repositories_reply, list):  # a refused pass: entries of {repository, error}
                    repositories_reply = {item.get("repository"): item for item in repositories_reply if isinstance(item, dict)}
                result = repositories_reply.get(name, {}) if isinstance(repositories_reply, dict) else {}
                after = history(name)
                old_ids = {item["id"] for item in (_entries(before) or [])}
                added = [item for item in (_entries(after) or []) if item["id"] not in old_ids]
                detail = None
                if len(added) == 1:
                    detail_status, detail, _ = command("activity", "--entry", added[0]["id"])
                    if detail_status != 0 or _internal(detail):
                        problem(f"activity detail for {name} failed with status {detail_status}")
                activity_problems = _activity_problems(name, result, before, after, detail)
                entry["activity"] = {"before": before, "after": after, "detail": detail,
                                     "ok": not activity_problems}
                for issue in activity_problems:
                    problem(f"pass {number} of {name}: {issue}")
                print(f"pass {number} {name}: status {status} in {elapsed / 60:.1f} min; "
                      f"files {result.get('files')}; chunks {result.get('chunks')}; "
                      f"changedDuringPass {result.get('changedDuringPass')}", file=sys.stderr)
                if status != 0:
                    problem(f"pass {number} of {name} ended with status {status}: {json.dumps(reply)[:600]}")
                if _internal(reply):
                    problem(f"pass {number} of {name} reported an internal fault")
                if helper is not None:
                    if helper.changed_at is None:
                        problem(f"the helper could not change {CHANGED_FILE} during the first pass of {name}")
                    expected = f"{name}:@artifact/{CHANGED_FILE}"
                    if expected not in (result.get("changedDuringPass") or []):
                        problem(f"the first pass of {name} did not name {expected} under changedDuringPass: "
                                f"{result.get('changedDuringPass')}")
                if number >= 2:
                    if number == 2 and name == last and not arguments.no_change:
                        if not result.get("changed") or result.get("changedDuringPass"):
                            problem(f"the second pass of {name} did not take the changed file up alone: "
                                    f"changed {result.get('changed')}, changedDuringPass {result.get('changedDuringPass')}")
                    elif result.get("changed"):
                        problem(f"pass {number} of {name} found changes in an unchanged repository")
                if number >= 2 and result.get("changedDuringPass"):
                    problem(f"pass {number} of {name} saw changes in an unchanged repository: {result.get('changedDuringPass')}")
        for template in COMMANDS:
            words = [word.format(last=last) for word in template]
            if words[0] == "read" and "mycel" not in arguments.repos:
                continue
            status, reply, elapsed = command(*words)
            report["commands"].append({"command": words, "status": status, "seconds": round(elapsed, 1),
                                       "reply": reply})
            print(f"{' '.join(words)}: status {status} in {elapsed:.1f} s", file=sys.stderr)
            if status != 0:
                problem(f"{' '.join(words)} ended with status {status}: {json.dumps(reply)[:600]}")
            if _internal(reply):
                problem(f"{' '.join(words)} reported an internal fault")
    except BaseException:
        report["ok"] = False
        report["problems"].append("the real-repository check did not complete")
        raise
    finally:
        if arguments.report is not None:
            arguments.report.parent.mkdir(parents=True, exist_ok=True)
            arguments.report.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        if not arguments.keep:
            if backend.creation_owned(database):
                backend.drop_database(database)
            _remove(work)
        else:
            print(f"kept database {database} and {work}", file=sys.stderr)
    print("check_real:", "ok" if report["ok"] else f"{len(report['problems'])} problems", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
