"""Finite recursive freshness over an immutable result scope.

The adapter owns exact disk/dependency reads and the existing ingest publication
boundary. This layer only schedules that work: it never selects more results,
requests a model, renews a dependency pin, or creates a new time allowance.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
import math
import time
from typing import Literal, Protocol

from ._errors import MycelError


FreshnessStatus = Literal['done', 'pending', 'busy', 'refused', 'failed']
_STATUSES = frozenset(('done', 'pending', 'busy', 'refused', 'failed'))
_TIME_LIMIT = 'The invocation freshness time limit was reached.'


class DeadlineExceeded(MycelError):
    def __init__(self):
        super().__init__('refused', _TIME_LIMIT)


@dataclass(frozen=True)
class Deadline:
    """One absolute monotonic expiry, created before initial discovery."""

    expires_at: float
    clock: Callable[[], float] = field(default=time.monotonic, repr=False, compare=False)

    def __post_init__(self):
        if (isinstance(self.expires_at, bool) or not isinstance(self.expires_at, (int, float))
                or not math.isfinite(self.expires_at) or not callable(self.clock)):
            raise MycelError('invalid_input', 'Freshness requires an absolute finite monotonic deadline.')

    @classmethod
    def after(cls, seconds: float, *, clock: Callable[[], float] = time.monotonic) -> Deadline:
        if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds) or seconds < 0 or not callable(clock)):
            raise MycelError('invalid_input', 'Freshness requires a finite nonnegative time allowance.')
        return cls(clock() + seconds, clock)

    def remaining(self) -> float:
        return max(0.0, self.expires_at - self.clock())

    def cancelled(self) -> bool:
        return self.remaining() <= 0

    def check(self) -> None:
        if self.cancelled():
            raise DeadlineExceeded()


def _names(values):
    if (not isinstance(values, tuple) or any(not isinstance(value, str) or not value
            or '\0' in value for value in values) or len(set(values)) != len(values)):
        raise MycelError('invalid_input', 'Freshness requires immutable distinct repository names.')


@dataclass(frozen=True)
class FreshnessScope:
    """Original search members; shared selections come from frozen settings."""

    repositories: tuple[str, ...]
    only: Literal['code', 'docs'] | None = None
    suppliers: tuple[str, ...] = ()

    def __post_init__(self):
        _names(self.repositories)
        _names(self.suppliers)
        if (not self.repositories or (self.only is not None and
                (not isinstance(self.only, str) or self.only not in {'code', 'docs'}))
                or (self.only == 'code' and self.suppliers)):
            raise MycelError('invalid_input', 'Freshness requires a nonempty supported result scope.')


@dataclass(frozen=True)
class DependencyFault:
    repository: str
    ref: str
    reason: str
    chunk: tuple[str, int] | None = None


@dataclass(frozen=True)
class ChunkRequirement:
    """Exact reachable sources/faults for one result or citation version."""

    repository: str
    chunk: tuple[str, int]
    repositories: tuple[str, ...]
    faults: tuple[DependencyFault, ...] = ()


@dataclass(frozen=True)
class FreshnessDiscovery:
    required_repositories: tuple[str, ...]
    faults: tuple[DependencyFault, ...] = ()
    dependencies: tuple[tuple[str, str], ...] = ()  # dependant repository, source repository
    chunk_requirements: tuple[ChunkRequirement, ...] = ()
    complete: bool = True
    reason: str | None = None


@dataclass(frozen=True)
class RepositoryUpdate:
    repository: str
    status: Literal['done', 'pending'] = 'done'
    reason: str | None = None


@dataclass(frozen=True)
class RefreshResult:
    status: FreshnessStatus = 'done'
    reason: str | None = None
    dependency_updates: tuple[RepositoryUpdate, ...] = ()
    # Captured declarations can reveal a source that the old index does not
    # know. Its owner remains pending until those sources were actually checked.
    discovered_repositories: tuple[str, ...] = ()
    dependencies: tuple[tuple[str, str], ...] = ()
    ingested: bool = False


@dataclass(frozen=True)
class RepositoryStatus:
    repository: str
    status: FreshnessStatus
    reason: str | None = None
    scan_required: bool = True


class FreshnessAdapter(Protocol):
    def discover(self, scope: FreshnessScope, *, deadline: Deadline) -> FreshnessDiscovery: ...
    def refresh(self, repository: str, *, deadline: Deadline) -> RefreshResult: ...


@dataclass(frozen=True)
class FreshnessResult:
    scope: FreshnessScope
    repositories: tuple[RepositoryStatus, ...]
    faults: tuple[DependencyFault, ...]
    finished: bool
    discovery_complete: bool
    incomplete_repositories: tuple[str, ...]
    chunk_requirements: tuple[ChunkRequirement, ...] = ()
    reason: str | None = None

    @property
    def dependency_complete(self) -> bool:
        return self.finished and not self.faults

    def complete_for(self, repository: str) -> bool:
        """Conservative repository check for callers without an exact key."""
        return self.discovery_complete and repository not in self.incomplete_repositories and any(
            row.repository == repository and row.status == 'done' for row in self.repositories)

    def complete_for_chunk(self, repository: str, chunk: tuple[str, int]) -> bool:
        """Unresolved refs or a pending reachable source never verify a result."""
        if not self.discovery_complete:
            return False
        requirement = next((item for item in self.chunk_requirements
            if item.repository == repository and item.chunk == chunk), None)
        if requirement is None or requirement.faults:
            return False
        states = {item.repository: item.status for item in self.repositories}
        return all(states.get(name) == 'done' for name in
                   {repository, *requirement.repositories})


def _validate_discovery(value):
    if not isinstance(value, FreshnessDiscovery):
        raise MycelError('internal', 'Freshness discovery returned incompatible work.')
    _names(value.required_repositories)
    if (not isinstance(value.faults, tuple) or any(not isinstance(item, DependencyFault) for item in value.faults)
            or not isinstance(value.dependencies, tuple) or any(not isinstance(edge, tuple) or len(edge) != 2
                or any(not isinstance(name, str) or not name for name in edge) for edge in value.dependencies)
            or not isinstance(value.chunk_requirements, tuple)
            or any(not isinstance(item, ChunkRequirement) for item in value.chunk_requirements)
            or type(value.complete) is not bool):
        raise MycelError('internal', 'Freshness discovery returned incompatible dependencies.')


def _validate_refresh(value):
    if (not isinstance(value, RefreshResult) or value.status not in _STATUSES
            or (value.status != 'done' and not value.reason)
            or type(value.ingested) is not bool or not isinstance(value.dependency_updates, tuple)
            or any(not isinstance(item, RepositoryUpdate) or item.status not in {'done', 'pending'}
                or not item.repository or (item.status == 'pending' and not item.reason)
                for item in value.dependency_updates)):
        raise MycelError('internal', 'Freshness publication returned incompatible work.')
    _names(value.discovered_repositories)
    if (not isinstance(value.dependencies, tuple) or any(not isinstance(edge, tuple) or len(edge) != 2
            or any(not isinstance(name, str) or not name for name in edge) for edge in value.dependencies)):
        raise MycelError('internal', 'Freshness publication returned incompatible dependencies.')


def _failure(error):
    if isinstance(error, DeadlineExceeded):
        return RefreshResult('pending', error.message)
    if isinstance(error, MycelError):
        status = ('busy' if error.code == 'busy' else 'refused' if error.code in
                  {'refused', 'settings', 'unknown_repository', 'invalid_input'} else 'failed')
        return RefreshResult(status, error.message)
    return RefreshResult('failed', 'The repository freshness check failed.')


def run_freshness(scope: FreshnessScope, adapter: FreshnessAdapter, *, deadline: Deadline,
                  no_fresh: bool = False) -> FreshnessResult:
    """Return a usable current-index fallback for every incomplete work path.

    Discovery always receives the original result scope. Upstreams are checked
    first. A newly captured ref can defer its owner's publication; that owner is
    retried only after one of its required sources actually completed new work.
    Downstream dependency-only updates never become file-scan requests.
    """
    if not isinstance(scope, FreshnessScope) or not isinstance(deadline, Deadline) or type(no_fresh) is not bool:
        raise MycelError('invalid_input', 'Freshness requires frozen scope, deadline and check intent.')
    seeds = tuple(dict.fromkeys((*scope.repositories, *scope.suppliers)))
    latest = FreshnessDiscovery(seeds, complete=False)
    scan_results: dict[str, RefreshResult] = {}
    updates: dict[str, RepositoryUpdate] = {}
    # The frontier overlay belongs to an unpublished captured owner. It is
    # discarded only once that owner publishes and stored discovery takes over.
    frontiers: dict[str, tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = {}
    attempts: dict[str, int] = {}
    completed: dict[str, int] = {}
    progress = 0
    discovery_reason = None
    interrupted = False

    def discover():
        nonlocal latest, discovery_reason, interrupted
        try:
            deadline.check()
            found = adapter.discover(scope, deadline=deadline)
            _validate_discovery(found)
            latest = found
            deadline.check()
            discovery_reason = found.reason
            return found.complete
        except KeyboardInterrupt:
            interrupted = True
            discovery_reason = 'Freshness checking was stopped by the caller.'
        except Exception as error:
            discovery_reason = (error.message if isinstance(error, MycelError) else
                                'Required source discovery failed.')
        latest = replace(latest, complete=False, reason=discovery_reason)
        return False

    def required():
        return tuple(dict.fromkeys((*seeds, *latest.required_repositories,
                                    *(name for names, _ in frontiers.values() for name in names))))

    ready = discover()
    while ready and not no_fresh:
        names = required()
        edges = set(latest.dependencies) | {edge for _, links in frontiers.values() for edge in links}
        candidates = []
        for name in names:
            if name not in attempts:
                candidates.append(name)
            elif name in frontiers and scan_results[name].status == 'pending':
                sources = set(frontiers[name][0]) - {name}
                if (sources and all(source in completed for source in sources)
                        and any(completed[source] > attempts[name] for source in sources)):
                    candidates.append(name)
        if not candidates:
            break
        # Repository cycles can contain valid acyclic chunk dependencies.
        # Select deterministically if no repository-level leaf is available;
        # the adapter and progress rule still keep unsuccessful cycles finite.
        required_set = set(names)
        leaf = next((name for name in candidates if not any(owner == name and source != name
            and source in required_set and source not in completed for owner, source in edges)), candidates[0])
        attempts[leaf] = progress
        try:
            deadline.check()
            outcome = adapter.refresh(leaf, deadline=deadline)
            _validate_refresh(outcome)
        except KeyboardInterrupt:
            interrupted = True
            outcome = RefreshResult('pending', 'Freshness checking was stopped by the caller.')
        except Exception as error:
            outcome = _failure(error)
        scan_results[leaf] = outcome
        # A completed owner pass applies its own dependency state. Earlier
        # source passes may have deferred that owner's update while its file
        # was dirty; only this new outcome can keep that work pending now.
        if outcome.status == 'done':
            updates.pop(leaf, None)
        for update in outcome.dependency_updates:
            updates[update.repository] = update
        if outcome.status == 'done':
            progress += 1
            completed[leaf] = progress
            frontiers.pop(leaf, None)
        elif outcome.status == 'pending' and outcome.discovered_repositories:
            frontiers[leaf] = outcome.discovered_repositories, outcome.dependencies
        if interrupted:
            latest = replace(latest, complete=False)
            discovery_reason = outcome.reason
            break
        # Even an unsuccessful check may have a committed prefix. Rereading
        # its explicit refs is required; an expired deadline never starts this.
        ready = discover()

    names = required()
    pending_reason = ('Freshness checking is disabled.' if no_fresh else discovery_reason or
                      'The required repository check has not completed.')
    rows = []
    for name in dict.fromkeys((*names, *updates)):
        scanned = scan_results.get(name)
        update = updates.get(name)
        if scanned is not None and scanned.status != 'done':
            status, reason = scanned.status, scanned.reason
        elif update is not None and update.status == 'pending':
            status, reason = 'pending', update.reason
        elif scanned is not None or (name not in names and update is not None):
            status, reason = 'done', None
        else:
            status, reason = 'pending', pending_reason
        rows.append(RepositoryStatus(name, status, reason, name in names or name in scan_results))
    unfinished = {item.repository for item in rows if item.status != 'done'}
    incomplete = unfinished | {fault.repository for fault in latest.faults}
    edges = set(latest.dependencies) | {edge for _, links in frontiers.values() for edge in links}
    while True:
        expanded = incomplete | {owner for owner, source in edges if source in incomplete}
        if expanded == incomplete:
            break
        incomplete = expanded
    if not latest.complete:
        incomplete.update(names)
    finished = bool(latest.complete and not no_fresh and not unfinished)
    return FreshnessResult(scope, tuple(rows), latest.faults, finished, latest.complete,
        tuple(sorted(incomplete)), latest.chunk_requirements, discovery_reason)
