# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Recursive scheduling, shared time budget and current-index fallback checks."""
from dataclasses import FrozenInstanceError, replace

from mycel._errors import MycelError
from mycel._freshness import (ChunkRequirement, Deadline, DeadlineExceeded,
    DependencyFault, FreshnessDiscovery, FreshnessScope, RefreshResult,
    RepositoryUpdate, run_freshness)

import unittest

from mycel._freshness import (
    Deadline,
    FreshnessDiscovery,
    FreshnessScope,
    RefreshResult,
    run_freshness,
)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Adapter:
    def __init__(self, discovery, outcomes=None, *, clock=None, discover_cost=0, refresh_cost=0):
        self.discovery = discovery
        self.outcomes = {name: list(values) for name, values in (outcomes or {}).items()}
        self.clock = clock or Clock()
        self.discover_cost, self.refresh_cost = discover_cost, refresh_cost
        self.events = []
        self.deadlines = []
        self.scopes = []
        self.current_index = ('indexed result before the check',)
        self.applied = []

    def discover(self, scope, *, deadline):
        self.events.append(('discover', deadline.remaining()))
        self.deadlines.append(deadline)
        self.scopes.append(scope)
        self.clock.advance(self.discover_cost)
        value = self.discovery() if callable(self.discovery) else self.discovery
        if isinstance(value, BaseException):
            raise value
        return value

    def refresh(self, repository, *, deadline):
        self.events.append((repository, deadline.remaining()))
        self.deadlines.append(deadline)
        self.clock.advance(self.refresh_cost)
        values = self.outcomes.get(repository)
        value = values.pop(0) if values else RefreshResult()
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, RefreshResult) and value.status == 'done':
            self.applied.append(repository)
        return value

    def read_index(self, result):
        # The caller can always perform its existing index read after an
        # incomplete check; discovery/refusal never replaces the result scope.
        return result.scope, self.current_index


def discovery(*names, edges=(), requirements=(), faults=(), **values):
    return FreshnessDiscovery(tuple(names), faults, edges, requirements, **values)


def statuses(result):
    return {row.repository: (row.status, row.reason, row.scan_required) for row in result.repositories}


class FreshnessTests(unittest.TestCase):
    def run_check(self, adapter, scope=None, *, seconds=5, no_fresh=False):
        return run_freshness(scope or FreshnessScope(('driver',)), adapter,
            deadline=Deadline.after(seconds, clock=adapter.clock), no_fresh=no_fresh)


# Archived complete imports; restore needed names in their original scope, not at this file tail.
