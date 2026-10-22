# Sylvan Stack

Sylvan Stack is a family of developer tools for working with code, its
documentation and AI coding agents. Its two products are **Mycel**, which keeps
a project's documentation tied to the code it describes, and **Arbol**, a macOS
application that runs several AI coding agents side by side. This page
describes the parts that are most interesting from an engineering point of
view.

## Documentation that knows when it is wrong

Documentation drifts away from code, and nobody notices until a reader is
misled. Mycel binds each section of a document to exact places in the code,
such as a function or a class, and records the exact version of that code the
section was last checked against. When the code changes, every document that
depends on it, directly or through other documents, is marked stale in the
same database transaction that records the change, with the full chain of
reasons.

A language model then judges whether the change actually breaks what the
document says. Its answer must come from an exact pinned model, in a strict
format, within hard limits; an uncertain answer goes to an independent
reviewer. A model's verdict alone never clears a warning: only an edit or an
explicit confirmation does.

Code: [`_staleness.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_staleness.py),
[`_evidence.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_evidence.py),
[`_jev.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_jev.py)

## Following code through renames

To keep those links valid, Mycel has to recognize a function after it has
been renamed, moved or edited. It parses Python, TypeScript, JavaScript and
Svelte, gives each declaration an identity that does not depend on its name,
and matches old declarations to new ones as a maximum bipartite matching in
three rounds of falling certainty: same name, earlier name, same content. A
weaker round can never take a match from a stronger one, so the result is
deterministic and explainable. A rename reported by Git is trusted only when
the file contents confirm it.

Code: [`_identity.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_identity.py)

## Search for both identifiers and questions

Mycel's search combines keyword ranking (BM25) with embedding similarity and
treats two kinds of query differently. A query that looks like an identifier is
ranked by reciprocal rank fusion of both signals. A question is ranked by
meaning, and a document that answers it lifts the code it describes. The same
index always returns the same order, and long texts are split to fit the
embedding model without ever being truncated.

Code: [`_retrieval.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_retrieval.py),
[`_ranking.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_ranking.py)

## RAPTOR summaries that stay current

A broad question such as "how does sign-in work here" has no single section
that answers it. For such questions Mycel builds a RAPTOR tree (Recursive
Abstractive Processing for Tree-Organized Retrieval). It groups document
sections by meaning, has a language model write one summary per group, then
groups and summarizes those summaries again, level by level. Search runs over
the whole tree at once, so a broad question lands on a summary and a precise
one on the section itself.

Mycel adds what the original method lacks for a code base that keeps changing:
- **Reproducible grouping.** Sections are grouped with PCA and Gaussian mixture
  models, with the number of groups chosen by BIC. A section may belong to
  several topics. Every source of numerical nondeterminism is pinned, so the
  same corpus always gives the same tree.
- **Incremental upkeep.** Each summary records the exact versions of the
  sections it was written from. When a section changes, only the summaries
  above it are marked stale, and regeneration rewrites just those, lowest
  level first.
- **Atomic replacement.** A new tree is written and embedded privately, then
  replaces the old one in a single transaction. A failed or interrupted build
  never leaves search with half a tree.

Code: [`_summary_grouping.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_summary_grouping.py),
[`_summary_build.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_summary_build.py),
[`_summary_regenerate.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_summary_regenerate.py)

## Specifications the code must prove

Every component is built from numbered specifications. Each test declares
which requirements it proves, and the specification text is pinned by hash, so
a changed requirement is noticed at once. A requirement counts as done only
when a test proving it actually ran and passed, and a release is refused while
any requirement is unproven. Database tests each get a throwaway PostgreSQL
database; unit tests cannot reach the network.

Code: [`_coverage.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_coverage.py)

## One contract for different AI coding agents

Arbol drives Claude Code, Codex and Pi, three tools with different protocols,
session formats and ways of failing, through one vendor-neutral contract: one
process per operation, a stream of numbered events and one set of errors. A
single black-box test suite checks every implementation against it, using
stand-ins that replay recorded vendor traffic.

Each agent's own conversation is resumed when the caller's history still
matches it, decided by an incremental fingerprint of that history, and rebuilt
from the history otherwise. The fingerprint stays correct even when a Unicode
surrogate pair is split between two chunks, and the Pi driver computes it
identically in Python and in JavaScript.

Code: [`conformance/`](https://github.com/sylvan-stack/arbol/tree/main/conformance),
[`continuity.py`](https://github.com/sylvan-stack/arbol-claude-driver/blob/main/src/arbol_claude_driver/continuity.py)

## Surviving crashes and runaway processes

Coding agents start shells, servers and sub-agents, and any of them can hang or
be killed. Every run and every lock is owned by a process identity made of its
PID and its start time, so a reused PID never passes as the owner. After a
crash, the next invocation claims the orphaned work and removes only what it
can still prove belongs to it. In the Pi driver, every child process must be
admitted into a write-ahead ledger before it starts, and a separate watcher
cleans up if the driver dies. A stop takes down whole process trees under one
deadline, and secrets are removed from streamed output even when they arrive
split across two chunks.

Code: [`state.py`](https://github.com/sylvan-stack/arbol-claude-driver/blob/main/src/arbol_claude_driver/state.py),
[`event_stream.py`](https://github.com/sylvan-stack/arbol-codex-driver/blob/main/src/arbol_codex_driver/event_stream.py)

## Concurrency without waiting

Mycel never waits for a lock. A conflict becomes an immediate "busy" answer
with nothing committed, and whether an earlier invocation is still alive is
read from PostgreSQL's own session table, without heartbeats. Arbol's chat
tables enforce "one open exchange per chat" with a constraint instead of a
lock, so two simultaneous messages collide inside the database. The build tool
serializes its writers with Lamport's bakery algorithm over plain files, with
no daemon.

Code: [`_locks.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_locks.py),
[`layout.sql`](https://github.com/sylvan-stack/arbol-root/blob/main/contract/1/layout.sql),
[`mutation.py`](https://github.com/sylvan-stack/arbol/blob/main/src/arbol_builds/mutation.py)

## Builds that qualify themselves

Mycel and Arbol's agent drivers are installed as numbered Builds, each with its
own pinned Python. A driver's Build becomes the default only after it passes
its tests, the full contract suite and one real request. Mycel's checks run against the installed program
inside a macOS sandbox that blocks the network and the source tree, so no
check can pass by accident. A failed Build never replaces a working one, and
going back to the previous Build is one command.

Code: [`_automatic.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel_build/_automatic.py),
[`service.py`](https://github.com/sylvan-stack/arbol/blob/main/src/arbol_builds/service.py)

## Many AI agents, one code base

The Stack is built by several AI coding agents working in parallel. Work is
planned as files; an agent claims a piece of it with an exclusive lock file
and works in its own isolated copy of the whole stack, and each piece lands as
one merge commit. An outside watcher with no AI in it measures every agent's
progress from its logs every five minutes. When something looks wrong, an
agent from the other vendor reviews the work, and its verdict counts only when
its evidence checks out against Git and the plan.
