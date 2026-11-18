"""A finite quiet-period check using the ordinary Mycel mutation commands."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from time import time_ns

from ._capture import observe_document_inputs
from ._cli import Invocation, Result
from ._embed import embed
from ._errors import MycelError
from ._ingest import ingest
from ._scope import Repository, RepositoryLocations
from ._summaries import handle_summaries


QUIET_SECONDS = 900
_NANOSECONDS = 1_000_000_000
_STATE_VERSION = 1
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class _Observation:
    digest: str
    since: int
    status: str

    @property
    def ready_at(self) -> int:
        return self.since + QUIET_SECONDS * _NANOSECONDS


def _load(path: Path) -> _Observation | None:
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise OSError
            payload = json.loads(stream.read(1024))
        if (not isinstance(payload, dict) or set(payload) != {"version", "digest", "since", "status"}
                or type(payload["version"]) is not int or payload["version"] != _STATE_VERSION
                or not isinstance(payload["digest"], str) or not _DIGEST.fullmatch(payload["digest"])
                or type(payload["since"]) is not int or payload["since"] <= 0
                or payload["status"] not in ("waiting", "retry", "complete")):
            raise ValueError
        return _Observation(payload["digest"], payload["since"], payload["status"])
    except FileNotFoundError:
        return None
    except (UnicodeError, ValueError, RecursionError):
        # Start another full quiet period when a prior observation cannot be trusted.
        return None


def _save(path: Path, state: _Observation) -> None:
    scratch = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".maintenance-", delete=False) as stream:
            scratch = Path(stream.name)
            json.dump({"version": _STATE_VERSION, **asdict(state)}, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(scratch, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if scratch is not None:
            scratch.unlink(missing_ok=True)


def _due_reply(repository: str, state: _Observation, **fields):
    eligible = datetime.fromtimestamp(state.ready_at / _NANOSECONDS, tz=timezone.utc)
    return {"repository": repository, "status": state.status,
            "eligibleAt": eligible.isoformat(), **fields}


def _maintain(invocation: Invocation, repository: Repository, path: Path) -> Result:
    name = repository.name
    settings = invocation.settings
    digest = observe_document_inputs(settings, repository)
    now = time_ns()
    previous = _load(path)

    def postpone(new_digest):
        state = _Observation(new_digest, time_ns(), "waiting")
        _save(path, state)
        return Result(_due_reply(name, state))

    if previous is None or previous.digest != digest or previous.since > now:
        return postpone(digest)
    if previous.status == "complete":
        return Result({"repository": name, "status": "unchanged"})
    if now < previous.ready_at:
        return Result(_due_reply(name, previous))

    # Persist the retry delay before starting any stage so process loss keeps it.
    _save(path, _Observation(digest, now, "retry"))

    def changed():
        settings.require_current()
        current = observe_document_inputs(settings, repository)
        return postpone(current) if current != digest else None

    def incomplete(stage, result=None, *, error=None):
        if error is None and result is not None:
            error = result.value.get("error") or result.value.get("repositories", {}).get(name, {}).get("error")
        retry = _Observation(digest, time_ns(), "retry")
        _save(path, retry)
        return Result(_due_reply(name, retry, stage=stage, **({"error": error} if error else {})),
                      1 if result is None else result.status or 1)

    stage = "ingest"
    try:
        delay = changed()
        if delay is not None:
            return delay
        result = ingest(replace(invocation, command="ingest", arguments=()))
        if result.status:
            return incomplete(stage, result)
        delay = changed()
        if delay is not None:
            return delay

        stage = "embed"
        arguments = ("--retry-failed",) if previous.status == "retry" else ()
        result = embed(replace(invocation, command="embed", arguments=arguments), _disk_documents_only=True)
        if result.status:
            return incomplete(stage, result)
        counts = result.value["repositories"][name]
        if counts["pending"] or counts["deferred"]:
            return incomplete(stage, result)
        delay = changed()
        if delay is not None:
            return delay

        stage = "summaries"
        summary = replace(invocation, command="summaries", arguments=("status",))
        result = handle_summaries(summary)
        if result.status:
            return incomplete(stage, result)
        stale = sum(level["stale"] for level in result.value["levels"])
        written = 0
        if stale:
            if not result.value["commandSet"]:
                return incomplete(stage, error={"code": "settings",
                    "message": "Stale summaries need a configured Narrator model adapter."})
            delay = changed()
            if delay is not None:
                return delay
            result = handle_summaries(replace(summary, arguments=("regenerate",)))
            if result.status or result.value["failed"] or result.value["blocked"]:
                return incomplete(stage, result)
            written = result.value["written"]
        delay = changed()
        if delay is not None:
            return delay
    except MycelError as error:
        return incomplete(stage, error=error.to_dict()["error"])
    except KeyboardInterrupt:
        return incomplete(stage, Result({}, 2), error={"code": "refused",
            "message": "Maintenance was interrupted."})

    _save(path, _Observation(digest, time_ns(), "complete"))
    return Result({"repository": name, "status": "complete",
                   "embedded": counts.get("sent", 0), "summariesWritten": written})


def handle_maintenance(invocation: Invocation) -> Result:
    """Check an explicitly selected repository and hold its lock through all stages."""
    settings = invocation.settings
    names = invocation.repositories
    if len(names) != 1 or invocation.arguments or invocation.all_repositories:
        raise MycelError("invalid_input", "Use mycel maintain --repo <name>.")
    name, = names
    if name in settings.values["organizations"]:
        raise MycelError("invalid_input", "Select a literal repository for maintenance.")
    repository, = RepositoryLocations(settings).named(name)
    if not repository.enabled:
        raise MycelError("refused", "The maintenance repository is disabled in settings.")
    repository.require_folders()
    embedding = settings.values["embedding"]
    target = (settings.values["store"]["address"], name)
    lock_key = sha256(json.dumps(target).encode("utf-8")).hexdigest()
    scope = (*target, str(settings.file.resolve()), embedding["model"], embedding["dimensions"])
    state_key = sha256(json.dumps(scope).encode("utf-8")).hexdigest()
    root = Path.home() / ".mycel" / "maintenance"
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise OSError
        descriptor = os.open(root / (lock_key + ".lock"), os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return Result({"repository": name, "status": "busy"})
            return _maintain(invocation, repository, root / (state_key + ".json"))
        finally:
            os.close(descriptor)
    except OSError:
        raise MycelError("io", "The private maintenance state could not be read or written.") from None
