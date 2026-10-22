# Sylvan Stack

**Tools for building software together with AI coding agents, made so that
what everyone knows about a code base stays true.**

AI coding agents now write a large share of new code. They are fast, but they
work from what they are told about a code base, and code, documentation,
specifications and decisions drift apart within days. Sylvan Stack takes on
both sides of that problem:

- **Mycel** keeps a project's knowledge (code, documentation, specifications
  and decisions) in one index that knows exactly which statement rests on
  which code, at which version, and notices when a statement stops being true.
- **Arbol** is a macOS application in which several AI coding agents from
  different vendors work side by side under one contract, with their accounts,
  conversations, processes and failures handled the same way.

This page describes the parts of the Stack that are most interesting from an
engineering point of view. It is not a manual, and it does not try to explain
the whole architecture.

## The components

| Component | What it is |
|---|---|
| [Mycel](https://github.com/sylvan-stack/mycel) | A command-line tool that indexes code and documentation in PostgreSQL, tracks what rests on what, searches, summarizes and detects drift |
| [Arbol](https://github.com/sylvan-stack/arbol) | The application, the conformance suite shared by all agent drivers, and the tool that builds and installs every component |
| [Claude Driver](https://github.com/sylvan-stack/arbol-claude-driver), [Codex Driver](https://github.com/sylvan-stack/arbol-codex-driver), Pi Driver | One program per AI coding agent, all speaking the same contract |
| [Root](https://github.com/sylvan-stack/arbol-root) | The chat database contract and its conformance suite |
| [Trunk](https://github.com/sylvan-stack/arbol-trunk) | Runs one exchange of a chat: starts the agent, saves what it says and stops it cleanly |
| [Classifier](https://github.com/sylvan-stack/arbol-classifier) | Has a text judged by a language model, within strict limits |
| [Design System](https://github.com/sylvan-stack/arbol-design-system) | The interface: components, pages and twelve themes, with automated accessibility checks |

## Engineering principles

The same rules run through every component:

- **Exact, not approximate.** Every statement about code names the exact
  version it was made about. Nothing is assumed to be "probably still current".
- **Refuse rather than guess.** Ambiguous input, a file that changed
  underneath, a busy lock or a newer data format ends in a clear, typed refusal
  with nothing changed, never in a best guess.
- **All or nothing.** A change is published in one transaction or not at all.
  A failed or interrupted operation leaves the previous state intact.
- **Deterministic.** The same input gives the same index, the same ranking and
  the same summaries, so behavior can be tested and compared.
- **Proven, not claimed.** Every requirement is tied to a test that must
  actually run and pass, and every agent driver must pass the same black-box
  suite.
- **Bounded.** Every operation has a deadline, every child process is
  accounted for, and every model call has hard limits.
- **Secrets stay secret.** Keys never appear in command lines, environments,
  logs or output.

## Mycel: knowledge that stays true

### Documentation that knows when it is wrong

Documentation drifts away from code, and nobody notices until a reader is
misled. Mycel binds each section of a document to exact places in the code,
such as a function or a class, and records the exact version of that code the
section was last checked against. When the code changes, every document that
depends on it, directly or through other documents, is marked stale in the
same database transaction that records the change. The warning carries the
full chain of reasons: which change, through which documents, to which
section.

Only a person clears a warning. Editing the document, or confirming that it is
still right, renews its pins atomically and records who verified what, against
which exact versions. That record of verifications survives later changes, so
"when was this last known to be right, and by whom" always has an answer.

Code: [`_staleness.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_staleness.py),
[`_evidence.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_evidence.py),
[`_verification.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_verification.py)

### A language-model judge that can be trusted

Stale does not mean wrong: most code changes leave the documentation true.
Mycel asks a language model whether a change actually breaks what a document
says, and treats that model as an unreliable component that has to be
contained:

- **Complete, replayable evidence.** Each request is built in canonical form
  from the old and new code, the dependent text and the documents that govern
  it, so every answer can be traced back to exactly what the model saw.
- **Strict answers.** The model must be the exact pinned version and must
  answer in a strict format within hard limits on time and size. Its
  confidence is recomputed from the returned probabilities instead of being
  taken on trust.
- **A second opinion.** An uncertain answer goes to an independent reviewer, a
  separate process identified by the hash of its program.
- **A safe pipeline.** Work is selected deterministically and runs in
  concurrent, bounded stages with leases. Transient failures are retried, work
  can be cancelled, and a result is applied only if nothing it read has
  changed meanwhile. A file must also have been quiet for a few minutes, so
  half-finished edits are never judged.
- **Advice, not authority.** A verdict never clears a warning on its own.

The whole pipeline can be evaluated offline on labelled cases, through the
production code path, with scripted stand-ins in place of the paid model and
the reviewer.

Code: [`_jev.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_jev.py),
[`_reviewer.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_reviewer.py),
[`_classification_runner.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_classification_runner.py)

### Code that knows why it exists

Mycel links a piece of code to the requirement or decision it implements, and
records each link with its method, confidence and author. Two questions that
usually take research become queries: which code rests on no requirement, and
which requirements no code rests on yet. Requirements and decisions are
addressed by stable UUID-based identifiers, so a link survives edits to the
specification and moves of the requirement, and a whole batch of links is recorded in one transaction or not at
all.

Code: [`_justify.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_justify.py),
[`_origins.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_origins.py)

### Following code through renames

To keep all these links valid, Mycel has to recognize a function after it has
been renamed, moved or edited. It parses Python, TypeScript, JavaScript and
Svelte, gives each declaration an identity that does not depend on its name,
and matches old declarations to new ones as a maximum bipartite matching in
three rounds of falling certainty: same name, earlier name, same content. A
weaker round can never take a match from a stronger one, so the result is
deterministic and explainable. A rename reported by Git is trusted only when
the file contents confirm it.

Code: [`_identity.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_identity.py)

### Every copy of the code, kept apart

Developers, and even more so AI agents, work in several copies of the same
code at once: the working folder, local branches, stashes and clones side by
side. Mycel indexes each of them as its own location. Identical content is
recognized as identical and stored once, while each location keeps its own
view, so an agent in one clone sees its own version of the code and its
documentation, not another agent's. A clone can also be compared with the
last merged main, to see exactly which links its changes affect.

Code: [`_capture.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_capture.py),
[`_location_corpus.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_location_corpus.py)

### Search for both identifiers and questions

Mycel's search combines keyword ranking (BM25) with embedding similarity and
treats two kinds of query differently. A query that looks like an identifier is
ranked by reciprocal rank fusion of both signals. A question is ranked by
meaning, and a document that answers it lifts the code it describes. The same
index always returns the same order, and long texts are split to fit the
embedding model without ever being truncated.

Search never silently answers from an outdated index. Before replying, it
checks the sources behind its results, and the sources those depend on, and
indexes again whatever changed, all within one time limit. Anything it could
not check in time is marked in the reply instead of being hidden.

Code: [`_retrieval.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_retrieval.py),
[`_ranking.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_ranking.py),
[`_freshness.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_freshness.py)

### RAPTOR summaries that stay current

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

### Measuring search quality

Changes to ranking are judged by measurement, not by impression. Evaluation
files list questions together with the results they must find. Mycel reports
recall for each kind of query, bound to fingerprints of the exact index and
settings that produced it, and compares two runs to show what a change
improved and what it broke.

Code: [`_evaluation.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_evaluation.py)

### Specifications the code must prove

Every component is built from numbered specifications. Each test declares
which requirements it proves, and the specification text is pinned by hash, so
a changed requirement is noticed at once. A requirement counts as done only
when a test proving it actually ran and passed, and a release is refused while
any requirement is unproven. Database tests each get a throwaway PostgreSQL
database; unit tests cannot reach the network.

Code: [`_coverage.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_coverage.py)

## Arbol: many AI coding agents in one application

### One contract for different AI coding agents

Arbol drives Claude Code, Codex and Pi, three tools with different protocols,
session formats and ways of failing, through one vendor-neutral contract. The
contract covers everything an application needs from an agent: accounts, each
with its own private home; models and usage limits; runs that stream answers,
reasoning, tool calls and questions as numbered events; stopping; and one set
of errors. Each operation is a separate process, so a driver holds no
resident state that could go wrong between calls.

A single black-box test suite checks every driver against the contract. It
never imports driver code: it runs each driver through its command line, with
throwaway home folders, local test servers and stand-ins that replay recorded
traffic of the real vendor tools.

Code: [`conformance/`](https://github.com/sylvan-stack/arbol/tree/main/conformance),
[`app_server.py`](https://github.com/sylvan-stack/arbol-codex-driver/blob/main/src/arbol_codex_driver/app_server.py)

### Resuming the agent's own conversation

When a chat continues, Arbol resumes the agent's own saved conversation if
the caller's history still matches it, and rebuilds the conversation from the
history otherwise. The decision rests on an incremental fingerprint of the
history, which stays correct even when a Unicode surrogate pair is split
between two chunks. The Pi driver computes the identical fingerprint in Python
and in JavaScript. Only identifiers and fingerprints are stored, never message
text, and the stored mapping changes only after a run succeeds.

Code: [`continuity.py`](https://github.com/sylvan-stack/arbol-claude-driver/blob/main/src/arbol_claude_driver/continuity.py),
[`history.py`](https://github.com/sylvan-stack/arbol-claude-driver/blob/main/src/arbol_claude_driver/history.py)

### Surviving crashes and runaway processes

Coding agents start shells, servers and sub-agents, and any of them can hang or
be killed. Every run and every lock is owned by a process identity made of its
PID and its start time, so a reused PID never passes as the owner. After a
crash, the next invocation claims the orphaned work and removes only what it
can still prove belongs to it. In the Pi driver, every child process must be
admitted into a write-ahead ledger before it starts, and a separate watcher
cleans up if the driver dies. A stop takes down whole process trees under one
deadline, and output keeps its order under load: a slow reader slows the
driver down instead of losing events.

Code: [`state.py`](https://github.com/sylvan-stack/arbol-claude-driver/blob/main/src/arbol_claude_driver/state.py),
[`processes.py`](https://github.com/sylvan-stack/arbol-claude-driver/blob/main/src/arbol_claude_driver/processes.py),
[`event_stream.py`](https://github.com/sylvan-stack/arbol-codex-driver/blob/main/src/arbol_codex_driver/event_stream.py)

### A chat that cannot be corrupted

Arbol's chat storage is designed so that neither concurrency nor crashes can
leave it inconsistent. The database itself guarantees that a chat has at most
one open exchange: two messages sent at the same moment collide in a
constraint, and the second gets a clean "busy" refusal. Retried writes never
duplicate a row, and an exchange is closed exactly once.

The program that runs an exchange is just as careful with its files: its
folder appears complete or not at all, and its event log is append-only. Its
supervisor ends the exchange exactly once on every path, including a failure
in its own code. Every time limit in the contract can be scaled down, so the
tests of these paths run in seconds and give the same result every time.

Code: [`layout.sql`](https://github.com/sylvan-stack/arbol-root/blob/main/contract/1/layout.sql),
[`run.py`](https://github.com/sylvan-stack/arbol-trunk/blob/main/trunks/trivial/src/arbol_trunk_trivial/run.py)

### Secrets handled like secrets

Keys never pass through a command line, an environment variable, a log or
an output. They travel from the macOS Keychain, or from a terminal prompt with
echo off, through standard input or an inherited pipe. Each agent account has its own private home, and child processes
see only an allow-listed environment. Streamed output is scrubbed of secrets
even when one arrives split across two chunks. Before a key is sent to a
non-default address, the program checks that the connection really ends on
this machine, so a DNS trick cannot redirect it. The local database server is
installed with least privilege, and its password verifier is computed by the
installer itself, so the server never sees the password in plain text.

Code: [`jev.py`](https://github.com/sylvan-stack/arbol-classifier/blob/main/src/arbol_classifier/jev.py),
[`owner_setup.py`](https://github.com/sylvan-stack/arbol-codex-driver/blob/main/src/arbol_codex_driver/owner_setup.py),
[`install_database_server.py`](https://github.com/sylvan-stack/arbol/blob/main/database/install_database_server.py)

### An interface built to be verified

The design system defines every component, pattern and page of the
application in Svelte and Storybook, with twelve themes built on a perceptual
(OKLCH) lightness scale. Every story is rendered in a real browser and fails on
any error. Text contrast is computed for each text and background pair of every
theme against WCAG, automated accessibility audits run on every page, layouts
are checked at phone and tablet widths, and keyboard checks cover focus traps
and the return of focus after a dialog closes.

Code: [`check-themes.mjs`](https://github.com/sylvan-stack/arbol-design-system/blob/main/scripts/check-themes.mjs),
[`check-interactions.mjs`](https://github.com/sylvan-stack/arbol-design-system/blob/main/scripts/check-interactions.mjs)

## Shared foundations

### Concurrency without waiting

Mycel never waits for a lock. A conflict becomes an immediate "busy" answer
with nothing committed, and whether an earlier invocation is still alive is
read from PostgreSQL's own session table, without heartbeats. Arbol's chat
tables enforce their rules with constraints instead of locks, so conflicts
are settled inside the database. The build tool serializes its writers with
Lamport's bakery algorithm over plain files, with no daemon.

Code: [`_locks.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_locks.py),
[`mutation.py`](https://github.com/sylvan-stack/arbol/blob/main/src/arbol_builds/mutation.py)

### Builds that qualify themselves

Mycel and Arbol's agent drivers are installed as numbered Builds, each with its
own pinned Python. A driver's Build becomes the default only after it passes
its tests, the full contract suite and one real request. Mycel's checks run
against the installed program inside a macOS sandbox that blocks the network
and the source tree, so no check can pass by accident. A failed Build never
replaces a working one, and going back to the previous Build is one command.
The launcher that starts a Build hands over the process unchanged, including
signals, arguments and a Ctrl-C pressed during start-up.

Code: [`_automatic.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel_build/_automatic.py),
[`service.py`](https://github.com/sylvan-stack/arbol/blob/main/src/arbol_builds/service.py),
[`launcher.py`](https://github.com/sylvan-stack/arbol/blob/main/src/arbol_builds/launcher.py)

### Porting without changing a byte

The agent drivers were rewritten from TypeScript to dependency-free Python
while their users' saved state kept working. A Python serializer reproduces
JavaScript's JSON output exactly, down to number formatting, key order and
broken Unicode, pinned by test vectors recorded from Node. The old and new
versions were then run against each other: shared accounts, competing
reservations, conversations continued in both directions and cleanup after a
killed owner.

Code: [`core.py`](https://github.com/sylvan-stack/arbol-claude-driver/blob/main/src/arbol_claude_driver/core.py),
[`migration/`](https://github.com/sylvan-stack/arbol/tree/main/migration)

## How the Stack is built

### Specifications first

Every component starts as written specifications: what it does, numbered
requirements with permanent identifiers, and decisions. An open question is
recorded with a proposed answer until it is decided, and the answer is kept
with its date. A shared glossary keeps one word for one thing across every
repository. The code then has to prove the specifications, as described
above.

### Many AI agents, one code base

The Stack is built by several AI coding agents working in parallel, from more
than one vendor. Work is planned as files, as a tree of larger and smaller
pieces, and each piece declares the folders and files it may change. An agent
claims a piece with an exclusive lock file that names it by process and start
time, so a claim whose agent has died is recognized and released. No piece
starts while its files overlap a claimed one. Each agent works in its own
isolated copy of the whole Stack, and each piece lands on main as one merge
commit, so exactly what it changed can always be seen.

### Supervision without AI in the loop

An outside watcher with no AI in it reads every agent's session log every five
minutes and measures the time and effort spent since the agent's last real
progress: a finished plan step, a commit or a message from a person. Its
thresholds come from measured data. When a signal fires, an agent from the
other vendor reviews the work, read-only and without tools, and must answer in
a fixed format. Its verdict counts only when its evidence checks out against
Git, the plan and the transcript.

### One set of instructions for every agent

Every agent, whatever its vendor, starts from one router document that sends
each kind of task to its guide. Skills are written once and installed for both
Claude Code and Codex, and the router reaches Codex's settings automatically
whenever it changes. The agents' built-in memory is switched off: whatever
must outlast a session is written into the documentation, where the next agent,
and Mycel, can find it.

## Technology

- **Languages:** typed Python 3.13 and 3.14, SQL, TypeScript,
  Svelte 5, JavaScript
- **Data:** PostgreSQL 17 with pgvector and ParadeDB search, psycopg 3
- **Retrieval and analysis:** tree-sitter, BM25, embedding models, NumPy,
  SciPy, scikit-learn
- **AI agents:** Claude Code, Codex and Pi, driven through their command lines
  and JSON-RPC
- **macOS:** launchd, Keychain, `sandbox-exec`, `libproc`
- **Interface:** Storybook, Vite, Playwright, axe-core
- **Tooling:** uv with locked, hash-pinned dependencies, mypy, Ruff, standalone
  pinned CPython builds
