"""Ingest real repositories into a throwaway store, twice, while a file changes.

The check any Beat can run (SYL-232). It reads the `readonly` clones of the
repositories it names and copies of their corpora, writes only to a database
of its own named `mycel_check_real_<id>` on the configured check server, and
drops it at the end. During the first pass of the last repository a helper
changes one Markdown file of the corpus copy: the pass must still complete and
name the file under `changedDuringPass`, and the second pass must take it up
(MYC-1.37). Then it runs `search`, `read`, `refs`, `stale`, `status` and
`embed --dry-run` on the result. Every command must end with status 0, and no
reply may carry the error code `internal`.

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


def _mycel(settings: Path, *arguments: str) -> tuple[int, dict | None, float]:
    started = time.monotonic()
    completed = subprocess.run([sys.executable, "-m", "mycel", *arguments],
                               env={**os.environ, "MYCEL_CONFIG": str(settings)},
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
                writing = connection.execute(
                    "SELECT count(*) FROM pg_catalog.pg_stat_activity WHERE datname = %s "
                    "AND backend_xid IS NOT NULL", (self.database,)).fetchone()[0]
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
              "commands": [], "ok": True, "problems": []}
    last = arguments.repos[-1]

    def problem(text: str) -> None:
        report["ok"] = False
        report["problems"].append(text)
        print("problem:", text, file=sys.stderr)

    try:
        repositories = {}
        for name in arguments.repos:
            code = arguments.clones.expanduser() / name
            artifact = work / "artifacts" / name
            artifact.parent.mkdir(exist_ok=True)
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
                helper = None
                if number == 1 and name == last and not arguments.no_change:
                    helper = Helper(backend, database, changed_path)
                    helper.start()
                status, reply, elapsed = _mycel(settings, "ingest", "--repo", name)
                if helper is not None:
                    helper.stop.set()
                    helper.join(timeout=5)
                entry = {"pass": number, "status": status, "seconds": round(elapsed, 1), "reply": reply}
                if helper is not None:
                    entry["helper"] = {"changed": helper.changed_at is not None, "file": str(changed_path),
                                       "waitedSeconds": None if helper.waited is None else round(helper.waited, 1)}
                report["repositories"].setdefault(name, []).append(entry)
                result = (reply or {}).get("repositories", {}).get(name, {}) if isinstance(reply, dict) else {}
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
                if number == 2:
                    if name == last and not arguments.no_change:
                        if not result.get("changed") or result.get("changedDuringPass"):
                            problem(f"the second pass of {name} did not take the changed file up alone: "
                                    f"changed {result.get('changed')}, changedDuringPass {result.get('changedDuringPass')}")
                    elif result.get("changed"):
                        problem(f"the second pass of {name} found changes in an unchanged repository")
                if number >= 2 and result.get("changedDuringPass"):
                    problem(f"pass {number} of {name} saw changes in an unchanged repository: {result.get('changedDuringPass')}")
        for command in COMMANDS:
            words = [word.format(last=last) for word in command]
            if words[0] == "read" and "mycel" not in arguments.repos:
                continue
            status, reply, elapsed = _mycel(settings, *words)
            report["commands"].append({"command": words, "status": status, "seconds": round(elapsed, 1),
                                       "reply": reply})
            print(f"{' '.join(words)}: status {status} in {elapsed:.1f} s", file=sys.stderr)
            if status != 0:
                problem(f"{' '.join(words)} ended with status {status}: {json.dumps(reply)[:600]}")
            if _internal(reply):
                problem(f"{' '.join(words)} reported an internal fault")
    finally:
        if arguments.report is not None:
            arguments.report.parent.mkdir(parents=True, exist_ok=True)
            arguments.report.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        if not arguments.keep:
            if backend.creation_owned(database):
                backend.drop_database(database)
            shutil.rmtree(work, ignore_errors=True)
        else:
            print(f"kept database {database} and {work}", file=sys.stderr)
    print("check_real:", "ok" if report["ok"] else f"{len(report['problems'])} problems", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
