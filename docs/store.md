# Private PostgreSQL store

`mycel init` is the only command that creates or changes the product schema.
`mycel info` reports its state, format, dimensions, generation and password-free
location, including unavailable, empty, foreign, damaged or newer stores. Plain
grep is available independently. Store-backed commands use the shared internal
guard to validate the store without DDL and hold a nonblocking structure lock
for their operation.

`status` reads repository location, stale and complete current-model coverage
counts in one read-only snapshot. `status --all` includes every indexed name,
including disabled or unknown settings names, with explicit `known`/`enabled`
flags. Reports neither allocate lock identities nor collect evidence or write
local caches. Source directories need not exist to inspect stored knowledge.

`repos remove` uses the exclusive repository mutation/removal guard and one
atomic repository-owned cleanup. Counts describe the rows actually removed;
source files and foreign dependant-owned evidence remain. Owning references
release before collection, and only wholly unreferenced evidence owned by the
removed repository is collected. A live lease or mutation refuses removal with
`busy`. Durable embedding receipts are removed with their repository even though
their table deliberately has no version foreign key. Numbered removal activity
belongs to no repository so the audit survives the cleanup it records.

The address comes only from the invocation's validated `store.address`. The
in-process native connection discards ambient PostgreSQL settings and alternate
authentication sources, resolves every address of the configured host, and
shares one finite connection deadline across attempts and credential acquisition.
It first sends no password. A server password challenge may read the fixed Mycel
store-password Keychain item once; cancellation also interrupts its bounded
reader. The private target and password reach no child program. Error replies
contain sanitized reasons, and the successful connection closes on every exit.

An empty private database needs server extensions `pg_search` and `vector`.
Initialization creates the Mycel tables, a BM25 index over the guarded chunk-version
search projection and a cosine HNSW index over embedding parts. It writes mandatory
format 3, dimensions and a fresh index-generation UUID, with no repository,
settings or feature-default rows. Numbered packages also record the exact
invocation and a completed global `init` audit in that schema transaction;
unnumbered development/fixture initialization writes the schema only. The generation stays fixed through normal
work, dimension changes and migrations. A lost-store rebuild gets a new one.

Initializing a lost store and ingesting current files recreates current located
content and new declared baselines. It does not recreate old asserted links,
relations, verification records, closed Drift work or classifier decisions, and
does not claim knowledge of changes before the rebuild. `info` and activity entry
details expose the new `indexGeneration`. An exact store backup can instead
preserve the original generation, pins, manifests, snapshots and recorded history;
current files alone cannot provide that evidence.

Complete exact chunk text is authoritative UTF-8 `source_bytes` in BYTEA; its
snapshot CHECK hashes those bytes. The BM25 `text` field replaces NUL with the
replacement character because PostgreSQL TEXT cannot contain NUL. A separate
CHECK binds that projection to the authoritative bytes. Resolver, evidence and
embedding readers use the bytes, including any NUL; the search field never
supplies displayed text, a baseline or model input. Saved embedding inputs and
serialized durable receipt payloads also use BYTEA, preserving exact inputs
through publication and recovery. Formats 2 and 3 preserve exact-byte storage.
Automatic initialization and migration checks use only disposable development
databases.

Compatibility checks read catalogues before any product table and inspect exact
relations, columns, keys, validated CHECK constraints and search-index definitions.
Foreign and version 1 tables are never read. A newer recorded format is reported
and refused with `store_format`, including unknown future structures. A compatible
same-format initialization performs no DDL and takes the shared structure guard;
an active exclusive initializer makes even that no-op return `busy`.

Format 1 is the first product format. There is no migration from format 0.
Format 2 changes verification ownership from a deletable exact version to its
logical chunk. The immutable record retains the exact version descriptor and
verification-owned dependant/source bytes and manifests. Old unlocated versions
still collect normally; surviving logical chunks keep their full verification
history. Dead chunks and repository removal release their record owners.

Only explicit `init` performs the consecutive transactional format 1→2
migration. It validates the exact predecessor catalogue, each legacy record's
logical ownership, exact dependant version, public evidence and record-owned
snapshots/manifests before changing columns. Missing or corrupt legacy evidence
refuses the whole step without inventing values or dropping records. The index
generation stays fixed. Numbered initialization includes its exact reply and
activity in the migration rollback boundary. Missing paths and newer formats
are refused. Only explicit init may
change dimensions: it removes old vectors and deferred result receipts, changes the vector column and rebuilds
its index, retaining exact text, parts, failures and generation. Until then, embed
refuses the mismatch and retrieval must explain its wording-only fallback.

Packaged dimension initialization commits its exact reply counts and audit with
the vector/index change. Audit failure rolls back the change with `internal`.
The fixed Build identity is immutable package data. Explicit source development
supplies no number through its exact development marker, which staging excludes
and isolated execution refuses. Missing or malformed installed identity returns
`internal` before a schema change.

The supported 2048 dimension setting retains full float vectors. Because pgvector
limits a plain vector HNSW index to 2000 dimensions, its index uses a halfvec
expression; retrieval must rerank candidates using the retained full vectors.
This follows the [pgvector 0.8.2 documentation](https://github.com/pgvector/pgvector/blob/v0.8.2/README.md#half-precision-indexing).
The packaged schema targets the tested ParadeDB 0.24.1 BM25 API; later versions
need a deliberately verified compatibility change.

Atomic writes and repeatable-read snapshots use explicit transaction helpers
on an idle autocommit connection. Run store compatibility preflight before a
write transaction, then retain its shared structure guard for the operation;
the inspection starts its own read-only repeatable-read transaction and cannot
change isolation inside an existing write transaction.
Connection-owned advisory locks separate structure changes, repository passes,
embedding, classification, summaries, removal/mutation and exact invocation
liveness. Advisory acquisitions use try-locks, and row guards use `NOWAIT` where
available. Unavoidable uniqueness, foreign-key and table contention uses
PostgreSQL's minimum positive lock timeout of 1 ms; a zero timeout would allow
waiting without a limit. Different repositories and a pass
plus an embed can coexist. Classification/summary callers retain their operation
and liveness guards during model work, taking the short pass lock only for capture
and publication. The [activity substrate](activity.md) binds injected feature writes and audit details
to these transactions. Public command producers use this same transaction
boundary for actual feature writes and their audit details.

Embedding publication uses durable returned-result receipts.
Each validated batch is saved before its short publication transaction. A busy
pass leaves the saved results deferred, with no extra provider send; a later
embed drains them first. Publication removes only results whose exact versions
were deleted and applies the remaining batch atomically. Deferred results are
not searchable vectors or complete coverage. The receipt table contains no
foreign key to deletable chunk versions or parts.

Genuine product-init and concurrent-store checks execute on the configured
disposable backend and provide named passing proofs for the scoped store and
lock requirements. Earlier SQL seams and exploratory schema probes supply
development evidence only. SYL-148 owns installed working-Build qualification
and atomic publication; see [checks](checks.md).

The configured local development server is the dedicated `mycel-postgres`
container at loopback port 55432, using ParadeDB 0.24.1/PostgreSQL 17 and
pgvector 0.8.2. Its role `mycel` has database-creation permission without
superuser rights. Server extensions are prepared in its template so generated
check databases inherit them. Mycel's store password is the fixed system
Keychain item; settings contain only the password-free address. Automatic
checks use separately created/removed databases and never open `mycel`.
The settings backup is kept beside the settings file. The server's durable
volume is `mycel-pgdata`; Mycel itself has no resident process.

Generated publication uses the chunk, index-location, dependency, evidence
and generated-state tables retained by format 3. Its SQL catalogue and
verification ownership are unchanged. Generated dependency rows use
`mycel-generated-pin-v1` state and permanent `generated` evidence owners,
separate from declared/asserted rows and invocation-owned private leases.
The [generated provenance guide](generated.md) specifies transaction composition,
final guards and public summary regeneration/removal.

## Format 3: requirement and decision entities (MYC-17)

Format 3 admits the chunk kinds `req` and `dec`: one chunk per recognised
requirement or decision row, whose identifier is the UUID written in the row's
HTML comment, with its exact versions and its disk locations like any chunk.
The pass publishes them beside the section chunks in the same file
transaction; a row that moves to another file keeps its chunk row and gains the
new file's location. Collection removes their unlocated versions like any
other, but never the chunk row itself, so a withdrawn id stays reserved. The
format step from 2 to 3 changes no table: it validates the format-2 structure
and that no entity chunk exists yet, then raises the number, so that an older
Build, which would read those chunks as code, refuses the store. `mycel init`
runs it in one transaction and `mycel info` reports `format: 3`.
