# Transaction-bound activity

The internal `MutationActivity` substrate records applied mutations over injected
transaction callers. Public ingest, embedding, summary generation and
classification connect their producers and exact committed reply counts. Public `activity` lists
ordered history and `activity --entry <id>` exposes one pass with its ordered
file, identity and classification details. Writer transactions retain bounded
history while preserving exact live invocations and independent evidence.

Activity requires the package's numbered Build identity. An unnumbered source
development run deliberately leaves no activity, including after an ingest that
changes the index; it never substitutes a number for a Build. A numbered package
with a missing or damaged identity fails with `internal` instead of falling back
to development behavior. Use the numbered package when checking public activity.

The public subprocess store checks run ingest, list and detail commands from a
private package copy with fictional Build `1a`. They compare the complete stored
counts with the repository's ingest reply, inspect code and document decisions,
require no new entry after a no-op, and force an audit write failure to prove
publication rolls back. `scripts/check_real.py` uses the same explicit test
identity on copies of real repositories in its own disposable store. Each
changing pass must add exactly one entry with matching counts and readable
details; an unchanged pass must preserve history. Its report labels the runtime
`numbered_test_package` and `qualifiedBuild: false`. These are automatic activity
checks, not creation, installation or qualification of a working Build.

Each entry also returns its persisted `indexGeneration` UUID. A fresh store
initialization and its later ingest entries share the new generation, so their
activity cannot impersonate work from a lost store. Reporting reads this identity
without changing activity or evidence.

The retained document-reference pass now supplies a real producer:
`DeclaredRefStore.recheck(..., activity=active_audit, reply_counts=caller_counts)` updates each affected
owner's dependency records, active edges and reference faults in the same
transaction as its `ingest` entry. The initiating repository may be a target
whose change affects declarations in other repositories. These dependency-only
entries contain `refsChecked`, `refsChanged` and `refFaults` reply counts, with
no fabricated file or identity details. The required pure `reply_counts`
callback receives the owner and local counts and supplies cumulative counts from earlier
committed replies. It previews counts inside the write transaction and must
not change caller state; the producer advances its counters after commit.
Final counts, including completed no-op checks, go to `audit.finish(counts=...)`.
An identical retry and read-only reference reporting leave no new entry. The caller supplies the
active session and an explicit Build identity on the exact writing connection;
development code does not manufacture an installed Build number.

A session holds the existing checked store guard and an exact invocation UUID,
allocated liveness key, backend PID/start time and index generation. It accepts
writes only from that same live connection. A different session, reused PID or
ordinary repository lock cannot protect another invocation's open entry.

`apply(repository, kind, caller)` runs the feature caller inside one atomic
transaction under repository removal protection. The caller returns a typed
`AppliedMutation` with its cumulative repository reply counts and actual change
status. A no-op leaves no activity. The first actual change creates the entry;
subsequent changes update its counts. Downstream dependency-only changes use
an `ingest` entry for that affected repository with no invented file details.
`record_in_transaction(repository, kind, AppliedMutation)` attaches an actual
mutation to a caller-owned native transaction without nesting or committing; retention takes only its short
nonblocking group row guard. It verifies the active exact invocation and connection-owned
structure/removal protection. Complete source publication uses it for foreign
dependency changes; source and downstream audit rows become visible together
and roll back together. A supplied no-op creates no entry. Multi-prefix callers
preview cumulative reply counts and advance their counters only after commit.
Three configured store checks verify shared visibility, late audit rollback and
retry, and idle/foreign/unprotected attachment refusal.

Only `init` and `remove` are global entries; removal counts name the removed
repository. Callers retain their required operation/pass locks and perform no
model work or independent commits inside the callback.

Applied files are root/path/location-qualified. Every code/document identity
decision belongs to a file applied in that same transaction. A rolled-back file
loses its feature writes and all audit details, including a first entry. Previously
committed files remain applied if a later file fails. Explicit `classify` entries
copy exact reply counts and retain bundle identifiers, typed dependant Places
and outcome summaries. Their table references activity only, so activity pruning
cannot delete or own classification evidence. Mechanical eligibility belongs to
`ingest`, and reports, evaluation, dry-runs and unchanged assertions provide no
mutation callback.

Closing records the final outcome/error and optional exact final repository
reply counts before releasing invocation liveness. Cancellation closes as
`stopped`; unexpected failures retain a sanitized `internal` error. Audit SQL
failures fail the command with `internal` and roll back that change. A failed
final close leaves the committed prefix open; after its session ends its
read-only diagnostic state is `unfinished`. Native connection loss has the
same effect without a daemon, timer or reaper. Activity inspection never
rewrites rows. Missing diagnostic entries return an internal `None`; the
public reader returns the closed `refused` error, as clarified by the owner on
15 October 2026.

The producer owns the final reply: `audit.finish(counts=...)` includes completed
checks that changed nothing after an earlier mutation. Every final portion is
validated and copied before any row closes. Supplying a reply for a repository
that never changed creates no entry. Invalid final portions leave all entries
open; a native failure during the last of several closes rolls the complete
close transaction back and can be retried while the exact invocation remains
live. Final nested reply values do not retain aliases to caller state.

Twelve configured disposable PostgreSQL checks cover lazy entries, downstream
counts, file/decision rollback and retry, partial failures, audit write/close
faults, owning-session termination, connection adoption refusal, global/no-op
behavior, classification references and cancellation. The five added producer
checks exercise real reference writes, settings-only edge deactivation and
faults without text changes, audit failure rollback and an applied owner prefix
followed by safe retry, and repeated passes with exact cumulative/final reply
accounting. They create no baseline or evidence owner.

Six further configured-store checks cover every supported kind, complete final
replies including unchanged scopes, refused prefixes, native classification
detail rollback, and one atomic close over several entries. They also cover
every file/identity change, including an unnamed introductory document chunk,
and inspect running/unfinished entries through an observer whose transactions
are read-only. Classification details are accepted only for `classify` and the
entry's repository; the activity row stores the bundle reference, Place and
outcome summary without becoming an evidence owner.

Packaged `mycel init` now reads its immutable package-local Build identity and
records one global `init` entry with the exact complete `InitReply`. Empty-store
creation bootstraps the invocation and its session-owned liveness key inside
the schema transaction. The outer guard retains liveness until that transaction
commits. Dimension changes use the ordinary invocation guard; the structure,
vector/receipt removal and completed audit commit together. A native audit
open/close failure returns `internal` and rolls back that schema change. A
compatible repeat opens no entry and allocates no invocation. Numbered package
identity is supplied by the staging registry, never an environment variable.
Unnumbered source/fixture initialization retains the schema-only development
API through an exact package-local development marker. Staging excludes that
marker and isolated execution refuses it. Missing or damaged installed identity
returns `internal` before schema changes; it cannot downgrade to development.
Source development manufactures no number and establishes no installed acceptance.

Seven configured store checks exercise actual command dispatch, empty bootstrap,
exact counts, no-op suppression, dimension rollback, damaged identity and
invocation-bootstrap failure. Three unit checks validate exact package identity.
Explicit schema migrations also record completed global `init` activity in
numbered Builds. SYL-148 owns complete installed working-Build qualification.

The complete located dependency producer now contributes separate reference,
pin, role and declaration-metadata counts to the same publication result and
activity entry. Optional guarded collection contributes its concrete deletion
counts; collection-only and evidence-only changes create activity even when
current file identities are unchanged. Policy, evidence, collection and audit failures roll back together.
Source/foreign-capture checks and a final publication recheck guard the complete
change. Public ingest incorporates these producer counters in its cumulative reply
and persisted activity counts.

Complete located publication also supplies automatic mechanical detection.
Its downstream reference and stale counters are merged before cumulative reply
callbacks and audit attachment, so one owner receives one exact `ingest`
portion. Detection-only foreign changes contain no file or identity details.
Busy or unchecked owners retain their marks and are returned with exact pending
places; a true reason-set no-op creates no activity. The optional `apply(...,
verify=callback)` runs the caller's final source/settings/catalog checks after
the initiating audit payload is attached, before commit. A final check or audit
failure rolls feature changes and every attached entry back together.

The SYL-112 boundary is this reusable mutation/liveness substrate over guarded,
injected transaction callers. Command-level ingest, embedding, generation,
classification and repository removal connect their producers and exact replies.
Numbered `repos remove` records actual counts in global `remove` activity within
the deletion transaction; that entry survives removal of the repository rows.
Public history and retention compose with this same substrate. Completing
automatic activity checks does not qualify a working installed Build.

## Reading one recorded pass

`mycel activity --entry <id>` reads a positive decimal store entry ID independently
of repository folders, including retained entries for a disabled repository. The
selector is exclusive with `--repo`, `--all`, `--kind` and `--k`. It returns one `entries` item
with string ID/invocation, hexadecimal Build, times, exact outcome/counts, files,
all identity decisions and classification references. Absent optional fields are
omitted. File/decision order includes root before path and location; renamed
decisions alone carry `previousName`. No UUID native value reaches JSON.

Inspection uses the guarded store's read-only snapshot. It neither calls a
provider nor captures files, changes timestamps, finishes entries or prunes
history. The same retained entry reads `running` while its exact invocation is
live and `unfinished` after an open entry loses that liveness. Missing/pruned
entries use the common closed `refused` code, following the owner's
15 October 2026 clarification of MYC-12. Four
focused checks cover malformed/exclusive selectors before any store access,
finite CLI help, all five ordered identity decisions and read-only liveness.

## Ordered history and bounded retention

`mycel activity [--repo <name> | --all] [--kind <kind>] [--k <count>]` lists
summary entries in descending start time, then descending entry ID. The default
is 25; a positive decimal count above 500 is capped at 500. Zero, negative or
malformed counts and unknown kinds return `invalid_input`. Empty lists succeed.
Use one repository explicitly or its folder. Organization and multiple-repository
selectors are invalid for this command. Explicit configured disabled/folderless
repositories and indexed orphan names remain inspectable. `--all` includes all
repository entries and the separate global `init`/`remove` entries.

Listing reads one repeatable read-only snapshot and fetches summaries without
loading each entry's files, decisions or classification details. `--entry` reads
those exact ordered details for one entry. Both compute `running` or `unfinished`
from the stored invocation's exact liveness and leave rows, versions and sequences
unchanged. They perform no freshness, model, pruning or evidence work.

Opening or closing an entry retains the newest 1,000 entries in that repository,
and global entries have a separate 1,000-entry limit. Start-time/ID order is the
same as listing. An older entry whose exact invocation remains live is protected,
even just after it closes, until that invocation ends; the next writer can then
prune it. Dead open entries follow ordinary retention. Each deleted entry loses
all attached file, identity and classification-reference details through the same
transaction. It never deletes the independent evidence those details reference.
Repository removal deletes that repository's activity with its indexed state and
keeps the global removal entry under the separate global limit.

The existing repository-state or global store row serializes each group's short
writer transaction without waiting or allocating another lock identity. Retention
requires a READ COMMITTED writer transaction so each statement after the group
lock sees committed activity rows. Repeatable-read or serializable writers are
refused before audit writes; no parent feature row is updated merely to coordinate
activity. Failure rolls back the feature change, audit details and pruning together.
Different repository groups retain independent guards. No timer, daemon, reader
cleanup or background collection is involved.

<!-- sources:
mycel:@code/src/mycel/_activity_retention.py#ActivityRetentionStore
mycel:@code/src/mycel/_activity.py#MutationActivity.record_in_transaction
mycel:@code/src/mycel/_activity.py#MutationActivity.finish
mycel:@code/src/mycel/_activity.py#record_initialization
mycel:@code/src/mycel/_activity_reader.py#activity_from_store
mycel:@code/src/mycel/_activity_reader.py#handle_activity
-->
