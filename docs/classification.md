# Canonical classification evidence

The internal classification producer assembles exact evidence for one selected
Drift reason. It launches no model or command. The [Jev adapter](jev.md) now
provides one bounded provider attempt and complete review routing. The
[reviewer adapter](reviewer.md) supplies the isolated process boundary.
`mycel classify` executes a finite selection explicitly. Ordinary ingest,
search and read use local guards and completed results without provider calls.

`ClassificationStore.prepare(settings, drift_id, reason_id, at=None)` captures
the pinned source, its complete current file/chunk/class family or explicit
disk absence, the exact current dependant, the other declared/asserted source
targets, and every document ancestor section. Required context is ordered by
canonical qualified address. An unavailable target is `context_missing`;
missing or corrupt retained evidence cannot be replaced by today's text.
Whole-file and family selections retain every required byte/member. Generated
index text remains ineligible as a declared/asserted source or relation target.

The protocol-1 decision includes the packaged `mycel-dependency-v1` instruction
and fixed label order, complete exact UTF-8 evidence, semantic selection
locators, Jev version, reviewer provider/model/revision/command hash and the
`mycel-drift-routing-v1` policy with canonical decimal confidence floor. Its
`input_hash` is SHA-256 of canonical UTF-8 JSON without an `inputHash` field.
`evidence_locators` is derived from supplied text and current selections.

The semantic projection omits capture time/location, full-file hashes and
extraction offsets. Full immutable manifests, snapshots, the exact decision
bytes and the complete evidence-bundle bytes remain owned by the dependant's
Drift. They create no searchable chunk, vector or location. File/time/settings
guards stay separate from semantic identity. Transport budgets change neither
the decision hash nor the fixed instruction/label order.

`ReviewCommandIdentity.inspect` expands/resolves only the executable argument,
preserves every other argument literally and hashes its complete executable
bytes. The identity includes immutable adapter revision, protocol 1,
`mycel-review-v1` and `mycel-review-env-v1`. An unavailable executable has a null
digest; independent Jev work can remain eligible, while review is blocked.
Inspection starts no child. `ReviewerRequest` contains the full decision,
derived allowed citations and explicit transport budget; transmitted bytes are
canonical JSON plus one LF, without truncation.

Eligibility uses the newest required live complete-file change time plus the
configured quiet period, default 300 seconds. Initially old trustworthy files
can qualify immediately. New bytes with preserved/restored timestamps, missing
timestamps and future timestamps use the first successful observation of that
exact version, with `timestamp_untrusted`. Repeated reads/cache use do not
restart it. First tombstones use their recorded UTC observation; a removed
section in a still-live file keeps both its tombstone and complete-file clocks.
The pure observation contract also accepts generated creation times. Pinned
immutable evidence never starts a live clock. No sleep, worker or timer is
installed; a later explicit invocation checks eligibility again.

`ClassificationStore.check(..., stage='jev'|'review'|'application'|'reuse')`
rechecks current disk versions, complete files and physical bindings, complete
resolved membership, required context, baseline identities, retained request
ownership/bytes, frozen settings, reviewer path/digest and eligibility. A
guarded result belongs only to those exact inputs. An unchanged preparation
reuses the original request capture identity; it does not manufacture new
manifests just because time passed.

`ClassificationStore.stage` holds the nonblocking classification lock and an
exact invocation-owned evidence lease. It releases all pass locks and writing
transactions before the caller's HTTP/subprocess work. The caller must finish
and clean up its attempt before leaving this context; the Jev adapter owns
bounded HTTPS and the reviewer owns process/protocol cleanup. The final launch
check follows lease publication. Jev and review have independent checks.

`ClassificationStore.apply` attaches a validated categorical result through
the existing Drift sink, rechecking canonical guards before effects and around
final publication. Obsolete results remain diagnostic attempts; no current
work effect, pin renewal, stale clearing or verification follows them.
`reuse` returns only a complete matching result whose fresh guards still pass,
spending no quota. A support judgement closes only its answered pair and
preserves mechanical staleness, baseline pins and owner confirmations.

The configured disposable-store checks exercise complete before/current and
governor/ancestor evidence, immutable owned canonical bytes, full-file quiet
periods, tombstones, missing/corrupt evidence, both call guards, executable and
settings changes, obsolete application races, guarded reuse and live evidence
leases. Unit fixtures separately exercise canonical byte/hash vectors,
transport separation, literal argv, source-family membership and pure UTC
observation rules without starting providers or resident work.

`mycel classify --repo <name> [--k <pairs>] [--dry-run]` selects current
on-disk source pairs in stable eligibility, dependant and semantic-input order.
Unclassified inputs precede retries at the same known eligibility time. The
configured candidate cap (or explicit `--k`), `at_once`, stage-attempt limits and
one monotonic command deadline apply together. Work-item, candidate-pair and
selected-work counts are separate; one dependant with three changed sources is
one work item and three candidates. Off-disk versions remain inactive.

The repository classification lock is held until all attempts end. Independent
HTTP/process work can overlap up to `at_once`; connection operations are
serialized through short guarded boundaries. Every attempt has an exact live
evidence lease, and no pass lock or writing transaction survives into provider
I/O. Typed transient faults alone retry with exponential backoff and bounded
`Retry-After`. Each retry rechecks and reclaims current inputs after the previous
attempt ends. Safe stage diagnostics and validated usage stay with the exact
decision; no raw provider diagnostic or child stderr is retained.

Deadline and SIGINT stop scheduling, cancel active adapters and join their
cleanup before repository liveness is released. Completed applications survive
in the printed partial reply. Faults, busy locks and unfinished selected
eligible work return status 1; ordinary debounce, unselected work and absent
reviewer configuration remain pending. No-work and completed selected work
return status 0. SIGINT returns status 2 with its partial reply. Completed
exact results pass the application guard again when reused and spend no calls.
Changed model, routing or command identities reopen policy-invalid support.
Actual classifications and their retained bundle references join the mutation
activity transaction; audit failure rolls back the corresponding result.

Dry-run uses native read-only snapshots and existing lock identities. It
holds the allocation guard while checking that configured repositories with
missing lock identities have no stored data. An unrelated empty repository
does not prevent inspection; missing guards on an indexed repository produce
a store diagnostic. It assembles the same complete canonical input without retaining snapshots,
updating observations/work, allocating an invocation or opening activity.
It acquires no credentials and starts no HTTP request or executable. A store
requiring password acquisition reports its normal store diagnostic instead.
Local executable reads can establish availability and fingerprint only:
reviewer readiness is `configured_unverified`, without a protocol/login claim.
Each pair reports eligibility, exact Jev HTTP bytes, complete reviewer request
bytes with the stated prospective `reviewTimeoutMs`, and bounded maximum stage
calls. Tokens and cost remain unavailable estimates without model-owned counts.

If a final audit or close fails after a repository returns, the command preserves
its completed repository replies, includes a safe invocation error and reports
`countsState: committed_prefix`. Remaining requested repositories are explicit
errors. Interruption keeps the same prefix and exits 2 after attempt cleanup.
