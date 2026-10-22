# Introduction

I am Vitalii Korsakov, a software developer. This page is for anyone who is
considering me for a role. It lists the most advanced techniques I use in the
Sylvan Stack, the family of repositories I design and build in the
[`sylvan-stack`](https://github.com/sylvan-stack) GitHub organization. Most
items link to the code that carries them.

## The Stack

- **Mycel** is a command-line tool that indexes code and its documentation in
  PostgreSQL. It records which document describes which code, at which exact
  version, and finds the documents that became wrong when the code changed.
- **Arbol** is a macOS application for working with several AI coding agents at
  once. It is built as separate programs:
  - three **Drivers**, which put the Claude Code, Codex and Pi coding agents
    behind one contract;
  - the **Root**, which holds the chat tables;
  - a **Trunk**, which runs one exchange of a chat;
  - the **Classifier**, which has a text judged by a language model;
  - the **Build tool**, which packages, checks and installs every component;
  - the **Design System**, which defines how the application looks.

| | |
|---|---|
| Languages | Python 3.13 and 3.14 with type hints, SQL (PostgreSQL 17), TypeScript, Svelte 5, Node.js modules |
| Size | about 150,000 lines of Python in eight repositories, of which about 68,000 are tests |
| Runtime dependencies | none in the Drivers, the Classifier and the Build tool, which use only the Python standard library; every Arbol component is checked with strict mypy and Ruff |
| Specifications | every component is written from numbered requirements; Mycel's registry alone holds 358 of them from 18 specification chapters |

## Correctness that is proven

**Requirements proven by executed tests.**
Each of Mycel's specification chapters is pinned into a requirement registry by
its SHA-256, so a changed specification is detected before any check runs.
Every test names the requirements it proves with a `@proves("MYC-…")`
decorator. It may prove only requirements of its own kind (unit, database,
evaluation or live), and it counts only when it ran and passed in the current
run. The release gate refuses any requirement left unproven. Unit checks patch
out all network access, including inside the database driver, and every
database check gets its own throwaway PostgreSQL database, so the checks run in
parallel worker processes. Today 353 of the 358 requirements are proven by
tests from a suite of 1,753; the other five need paid live runs.
[`_coverage.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_coverage.py),
[`requirements.json`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/data/requirements.json),
[`claims.json`](https://github.com/sylvan-stack/mycel/blob/main/checks/claims.json)

**One contract, several implementations, one black-box suite.**
The three Drivers wrap three different vendor tools but obey one contract: one
process per operation, JSON events on standard output and a fixed set of error
codes. One suite of 38 scenarios drives each Driver only through its command
line and imports none of its code. It uses throwaway home folders, loopback
test servers and, for each vendor tool, a stand-in that replays recorded
protocol traces and logs what it was given. It compares JSON by JavaScript's
rules (`undefined` is not `null`, every number is a double), so its verdicts
match those of the TypeScript suite it replaced.
[`conformance/`](https://github.com/sylvan-stack/arbol/tree/main/conformance)

The Root's SQL contract has a suite of its own. Each scenario gets a private
PostgreSQL server made with `initdb` and reachable only through a Unix socket.
After every scenario, a snapshot of 14 kinds of catalogue object is compared
with the one taken right after the schema was applied. Races are made
reproducible by holding `LOCK TABLE … IN SHARE MODE` open from a second
session.
[`rct_conformance/`](https://github.com/sylvan-stack/arbol-root/tree/main/contract/conformance/rct_conformance)

**A byte-compatible port from TypeScript to Python.**
The Claude and Codex Drivers moved from TypeScript to Python without changing
a byte of their stored state. A Python serializer reproduces `JSON.stringify`
exactly: number formatting, the order of integer-like keys and lone
surrogates. Fixtures generated with Node 24 pin the output, and a state format
newer than the program is refused before anything changes. The two versions
were then run against each other through their command lines: shared
accounts, competing reservations, continuing a conversation in both directions
and cleanup after a killed owner.
[`core.py`](https://github.com/sylvan-stack/arbol-claude-driver/blob/main/src/arbol_claude_driver/core.py),
[`migration/`](https://github.com/sylvan-stack/arbol/tree/main/migration)

## PostgreSQL: concurrency and integrity

**Concurrency control that never waits.**
Mycel's writers take `pg_try_advisory_lock`, shared or exclusive, in named
namespaces whose keys the store allocates, so two namespaces cannot collide.
Row locks use `FOR UPDATE … NOWAIT`, each transaction runs with
`lock_timeout = '1ms'`, and any conflict becomes a typed `busy` reply with
nothing committed. Reports read from `REPEATABLE READ, READ ONLY` snapshots.
Whether an earlier invocation is still running is decided without heartbeats:
it holds an advisory lock, and its backend's process ID and start time still
match a row of `pg_stat_activity`.
[`_locks.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_locks.py)

**Invariants in the schema, not in locks.**
In Arbol's chat tables, a partial unique index allows one open exchange per
chat, so two simultaneous messages to one chat collide in the database. The
Trunk reads which constraint fired and refuses with `chat_busy`. Two-way CHECK
constraints such as `(state = 'open') = (ended_at IS NULL)` keep states
consistent, every insert is `ON CONFLICT DO NOTHING` so a retry never
duplicates a row, and the final `UPDATE … WHERE state = 'open'` ends an
exchange exactly once.
[`layout.sql`](https://github.com/sylvan-stack/arbol-root/blob/main/contract/1/layout.sql),
[`database.py`](https://github.com/sylvan-stack/arbol-trunk/blob/main/trunks/trivial/src/arbol_trunk_trivial/database.py)

**Content-addressed provenance with exact pins.**
When a document is checked against the code it describes, Mycel keeps the exact
bytes it was checked against. Each comparison names its hash revision:
`sha256-exact-v1`, or a Unicode-normalized form that also records the Unicode
version. Evidence is serialized as canonical JSON (sorted keys, no floats,
cycles refused), and a stored snapshot is rebuilt only when its byte length and
SHA-256 both match. A pin is never renewed implicitly; only an explicit,
guarded `confirm` renews it.
[`_evidence.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_evidence.py)

**Staleness that follows the dependency graph.**
When code changes, every document that depends on it, directly or through
other documents, is marked stale in the same transaction that records the
change. The traversal is Kahn's topological order over declared, asserted and
generated edges. It keeps every distinct reason with the path it travelled, so
a diamond-shaped dependency keeps both of its paths, and a cycle is refused.
[`_staleness.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_staleness.py)

**A store that checks its own shape.**
Mycel's 32 tables are declared in code and compared with the PostgreSQL
catalogue before use: columns, constraints, normalized CHECK expressions and
index definitions. A store format number makes an older program refuse a
newer store, and a migration is explicit and validated first.
[`_store.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_store.py)

## Algorithms

**Identity of code across renames.**
Mycel follows a function or class through edits and renames. Python is parsed
with `ast`, TypeScript and JavaScript with tree-sitter, Svelte with a
hand-written scanner. The rename key is a SHA-256 over length-prefixed parts of
the declaration with only the name erased. Old and new declarations are matched
in three rounds (current name, earlier name, content), each a deterministic
maximum bipartite matching found with breadth-first augmenting paths, and no
later round can take a match from an earlier one. A rename reported by Git is
accepted only when both complete blobs agree byte for byte.
[`_identity.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_identity.py),
[`_code.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_code.py)

**Hybrid retrieval.**
Search combines exact BM25 (k1 = 1.2, b = 0.75, smoothed IDF) over text, name
and path with the best cosine similarity among each text's embedded parts.
Queries that look like identifiers are ranked by reciprocal rank fusion
(k = 60). Questions are ranked by cosine tiers with a document-to-code bridge,
which lifts the code that a matching document describes. Floating-point
boundaries are compared with a tolerance in ULPs and ties break on a fixed key,
so the same index always gives the same order.
[`_retrieval.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_retrieval.py),
[`_ranking.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_ranking.py)

**Lossless, token-budgeted embedding.**
A text longer than the embedding model's token budget is split at line or
blank-line boundaries, found by binary search over the token offsets, and at
single characters only when no boundary fits. Nothing is ever truncated, every
part keeps byte offsets into the original UTF-8 text, and the tokenizer is
pinned by revision and SHA-256.
[`_embedding_plan.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_embedding_plan.py)

**Deterministic hierarchical summaries.**
Document sections are grouped level by level, up to five levels: PCA down to at
most ten dimensions, then spherical Gaussian mixtures whose number of groups is
chosen by BIC. Membership is soft: a section joins every group it belongs to
with a probability of at least 0.10. A fixed seed and single-threaded
BLAS/OpenMP fix the order of the arithmetic, so the same input always gives the
same tree.
[`_summary_grouping.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_summary_grouping.py)

**Bounded language-model judgements with an independent reviewer.**
Whether changed code still supports a document's claim is judged by a language
model under hard limits: one attempt, a timeout, byte caps, a strict reply
schema and the exact pinned model version. Confidence is recomputed from the
returned probabilities with `Decimal` arithmetic. A low-confidence answer goes
to an independent reviewer process, identified by the SHA-256 of its
executable, and the inputs are checked again after a quiet period and once more
before anything is sent. A verdict never clears a stale mark; only an edit or
an explicit confirmation does.
[`_jev.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_jev.py),
[`_reviewer.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_reviewer.py)

## Processes, signals and crash safety

**Run ownership that survives crashes and reused process IDs.**
Every run and every lock in the Drivers is owned by a process identity made of
the PID and the kernel's start time, so a reused PID never passes as the owner.
Records are created exclusively with `os.link` and replaced atomically: `fsync`
of the file and of its folder, then `os.replace`. A stale lock is reclaimed
through an inode-checked marker, so two reclaimers cannot delete a lock that
someone has just taken. When a Driver is killed, the next invocation claims
the orphaned run, checks the record again before every step, and removes only
what its claim still matches.
[`state.py`](https://github.com/sylvan-stack/arbol-claude-driver/blob/main/src/arbol_claude_driver/state.py),
[`continuity.py`](https://github.com/sylvan-stack/arbol-claude-driver/blob/main/src/arbol_claude_driver/continuity.py)

**Write-ahead admission of every child process.**
In the Pi Driver (a private repository), every shell, MCP server, sub-agent or
network resource the agent wants to start must first be admitted into a
durable ledger. The ledger enforces a typed parent/child graph, gapless
sequence numbers per source, and messages bound to a nonce and an epoch. A
separate watcher process cleans up the admitted process groups when the Driver
dies. Process identity comes from Darwin's `libproc`, called through `ctypes`
with a check of the structure size.

**Bounded shutdown of process trees.**
Each vendor tool starts in its own session. A wrapper placed in `$SHELL`
records the PID and start time of every shell the tool spawns. A stop signals
only the process groups whose leader still has the recorded identity, and
escalates from SIGTERM to SIGKILL after two seconds under one absolute
deadline. The Codex Driver interrupts the main turn and every sub-agent turn at
once. A stop can come from a signal, a control line, the end of control input
or a closed output pipe.
[`processes.py`](https://github.com/sylvan-stack/arbol-claude-driver/blob/main/src/arbol_claude_driver/processes.py),
[`run.py`](https://github.com/sylvan-stack/arbol-codex-driver/blob/main/src/arbol_codex_driver/run.py)

**An ordered event stream with backpressure and live redaction.**
Standard output is non-blocking, and writes are chained tasks that wait on
`loop.add_writer`, so a slow reader slows the Driver down instead of
reordering or losing events. Every event carries a gapless sequence number, and
exactly one `finished` event ends the stream. A streaming scrubber holds back
the longest suffix that could be the start of a secret, so a key split across
two deltas never appears, even when the reader joins them.
[`event_stream.py`](https://github.com/sylvan-stack/arbol-codex-driver/blob/main/src/arbol_codex_driver/event_stream.py),
[`owner_setup.py`](https://github.com/sylvan-stack/arbol-codex-driver/blob/main/src/arbol_codex_driver/owner_setup.py)

**Resuming the vendor's own conversation.**
An incremental SHA-256 over the caller's history decides whether the vendor's
saved conversation can be resumed or must be rebuilt, and gives an ordered list
of reasons. The map stores only identifiers and digests, and it changes only
after a successful run. The digest holds back a trailing high surrogate, so a
UTF-16 pair split across chunks hashes like the joined text. The Pi Driver
computes the identical fingerprint in Python and in Node.
[`history.py`](https://github.com/sylvan-stack/arbol-claude-driver/blob/main/src/arbol_claude_driver/history.py)

**A two-way JSON-RPC client with backpressure.**
The Codex Driver speaks newline-delimited JSON-RPC with the Codex app-server
over its standard streams. It matches responses to futures by ID, answers the
server's own requests (`-32601` when unsupported), limits a line to 4 MiB,
decodes UTF-8 incrementally, and caps its notification queue at 16 MiB or
4,096 messages, pausing the reader when the queue is full.
[`app_server.py`](https://github.com/sylvan-stack/arbol-codex-driver/blob/main/src/arbol_codex_driver/app_server.py)

**A single-threaded supervisor for one exchange.**
The Trunk drives an agent process from one asyncio loop. Its waits are timed on
`CLOCK_UPTIME_RAW`, a stop escalates to SIGKILL after 16 seconds, and output
is still drained for a bounded time after the agent exits, because a
grandchild can hold the pipe open. A separate task saves rows in order and
reconnects after a failure, and the exchange ends exactly once on every path.
The exchange's folder is built under a hidden name and renamed into place,
events are appended with one `write(2)` per line, and every wait in the
contract can be divided by a test time scale, so the tests are fast and
repeatable.
[`run.py`](https://github.com/sylvan-stack/arbol-trunk/blob/main/trunks/trivial/src/arbol_trunk_trivial/run.py),
[`saver.py`](https://github.com/sylvan-stack/arbol-trunk/blob/main/trunks/trivial/src/arbol_trunk_trivial/saver.py),
[`folder.py`](https://github.com/sylvan-stack/arbol-trunk/blob/main/trunks/trivial/src/arbol_trunk_trivial/folder.py)

## Security

**Secrets never in arguments, environment or output.**
Keys are stored in the macOS Keychain by giving `security -i` a line on
standard input, never an argument, because other programs can read a running
program's arguments. A `Secret` type hides its value when printed. Child
processes see only an allow-listed environment and a private home folder per
account. The Pi Driver passes a key through an inherited pipe and zeroes the
buffer after reading it. When the Classifier is pointed at another endpoint,
it checks that the connected socket's peer address is a loopback address,
which defeats DNS tricks that would send the key elsewhere.
[`_credentials.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_credentials.py),
[`subscriptions.py`](https://github.com/sylvan-stack/arbol-claude-driver/blob/main/src/arbol_claude_driver/subscriptions.py),
[`jev.py`](https://github.com/sylvan-stack/arbol-classifier/blob/main/src/arbol_classifier/jev.py)

**A database server installed with least privilege.**
The local PostgreSQL server is created with data checksums, kept running by
launchd, and reachable only on loopback; a probe checks IPv4 and IPv6. It is
used through a role without superuser, role-creation, replication or
row-security-bypass rights. The installer generates the password, stores it in
the Keychain through standard input, and computes the SCRAM-SHA-256 verifier
itself (PBKDF2-HMAC, RFC 7677), so the server never sees the plain password.
[`install_database_server.py`](https://github.com/sylvan-stack/arbol/blob/main/database/install_database_server.py)

**Bounded child processes.**
Every process Mycel starts gets a fresh minimal environment, its own process
group, capped output (1 MiB of standard output, 64 KiB of errors), allow-listed
Git arguments and a deadline that ends in SIGTERM and then SIGKILL.
[`_safeguards.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel/_safeguards.py)

## Release engineering

**Reproducible numbered Builds.**
Mycel, the Drivers and the Classifier are installed as numbered Builds, each
with its own CPython pinned by URL and SHA-256. Mycel's wheels are pinned by hash and installed by
its own installer, which checks every RECORD entry and refuses path escapes
and case-folding collisions. The installed tree is made read-only and recorded
in a manifest of every file. Build numbers come from an fsynced journal and are
never reused.
[`_core.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel_build/_core.py),
[`build-lock.json`](https://github.com/sylvan-stack/mycel/blob/main/packaging/build-lock.json),
[`service.py`](https://github.com/sylvan-stack/arbol/blob/main/src/arbol_builds/service.py)

**Qualification before a Build becomes the default.**
A Driver Build becomes the default only after its unit tests, all 38
conformance scenarios and exactly one real message pass. A failed Build keeps
its number and its log and leaves the previous default in place. Mycel runs its
checks against the installed program inside a `sandbox-exec` profile that
denies all network except loopback and makes the source checkout unreadable,
so no check can pass by reaching the source tree. Withdrawing a Build rolls
back to the previous one.
[`_automatic.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel_build/_automatic.py),
[`_maintenance.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel_build/_maintenance.py)

**Launchers that add almost nothing.**
Arbol's launcher is one standalone Python file, made by joining modules after
removing their relative imports with Python's `ast`. It runs Python isolated
(`-ISB`), restores the default SIGPIPE and SIGXFSZ handling, and replaces
itself with the selected Build through `execv`, adding a median of 15 ms. Tests
send 100 Ctrl-Cs at varying moments of start-up and lose none, and check that
arguments and environment pass byte for byte, duplicates included, through a
raw `execve` made with `ctypes`. Mycel's launcher selects the newest intact
working Build and takes a shared lock on it that the program inherits across
`execv`, so a Build cannot be pruned while it runs.
[`launcher.py`](https://github.com/sylvan-stack/arbol/blob/main/src/arbol_builds/launcher.py),
[`_launcher_runtime.py`](https://github.com/sylvan-stack/mycel/blob/main/src/mycel_build/_launcher_runtime.py)

**Lamport's bakery algorithm over files.**
Changes to Build records are serialized with no resident process, one ticket
file per invocation. A dead writer is detected and its ticket removed in a way
that can never remove a new writer's ticket, and the file format matches the
earlier Node.js tool's, so the two exclude each other while both are installed.
A test runs four processes that each make 20 read-sleep-write increments and
requires exactly 80.
[`mutation.py`](https://github.com/sylvan-stack/arbol/blob/main/src/arbol_builds/mutation.py)

## Interface engineering

**A tested design system with twelve themes.**
Twelve themes are built on an OKLCH lightness ladder with equal accent chroma
and semantic tokens, in Svelte 5 and Storybook. Playwright renders all 229
stories in parallel and fails on any page error. Text contrast is computed in
the browser for 300 text and background pairs (the lowest is 4.56:1, above
WCAG AA), axe-core runs the WCAG 2.1 AA rules, every page is checked for
overflow at 390 and 768 pixels, and keyboard checks cover focus traps and the
return of focus to the control that opened a dialog.
[`check-themes.mjs`](https://github.com/sylvan-stack/arbol-design-system/blob/main/scripts/check-themes.mjs),
[`test-storybook.mjs`](https://github.com/sylvan-stack/arbol-design-system/blob/main/scripts/test-storybook.mjs),
[`check-interactions.mjs`](https://github.com/sylvan-stack/arbol-design-system/blob/main/scripts/check-interactions.mjs)

## Running a multi-agent engineering operation

I build the Stack with several AI coding agents, Claude Code and Codex, working
in parallel under a system of specifications, leases and outside supervision
that I designed.

**Specifications first.**
Every component is written from numbered specifications whose requirements
keep permanent identifiers such as `MYC-1.4`. An open choice is recorded as a
decision with a proposed default and is answered by me, with the date. The
code then proves the requirements as described above. One glossary of about
200 terms keeps one word for one thing across all repositories.

**Work as files, with leases.**
Planned work is a tree of files: Sagas contain Arcs, and Arcs contain Beats, the
units one agent finishes. Each Arc declares the folders and files it may
change. An agent takes a Beat by creating a hold file that cannot already
exist, naming itself by PID and process start time. A hold whose owner is gone
is released, and no Beat starts while its files overlap a held one. Ten
isolated working copies of the whole Stack are booked under `flock`; a copy
counts as free only when every repository in it is clean and on `main`. Each
Beat lands as one `--no-ff` merge commit, so `git diff <merge>^1 <merge>` is
exactly what it changed.

**Supervision with no AI in the loop, and cross-vendor review.**
A launchd job runs every five minutes. It reads every agent's session log
incrementally, joins sub-agents to their parents, and measures the time and
tokens spent since the last real progress: a ticked plan step, a commit or a
message from me. Its thresholds come from measured data, and a replay mode runs
it again over past logs. Each signal starts a review by the other vendor's
agent, read-only and without tools, which must answer in a fixed JSON schema.
A verdict counts only when at least two of its evidence points check out
against Git, the plan or the transcript.

**Documentation bound to code.**
Documents carry `sources` comments that name an exact place in the code, such
as `mycel:@code/src/mycel/_grep.py#handle_grep`. Mycel turns these into the
dependency graph described above, so a document that drifts from its code is
found mechanically, not by rereading it.
