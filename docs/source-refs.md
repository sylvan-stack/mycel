# Stored source declarations and bindings

The source declaration and central typed resolver APIs complete SYL-107
over the current core store and exact file/chunk locations. The public `refs` command
reports those retained observations. Public `derive` assertions and selection-specific withdrawal now use those exact
location/evidence guards. Complete public ingest composes those guarded producers;
`confirm` renews checked direct pins and records separate verification evidence.
These source APIs and reports perform no provider call.

## Public reference report

```sh
mycel refs --repo cellar
mycel refs --repo cellar --unresolved
```

Without `--unresolved`, the command lists every retained declared occurrence
owned by each selected repository, including repeated spellings and resolved
refs. The flag selects every stored resolution fault: malformed, ineligible,
unknown/disabled, missing, ambiguous and not-yet-checked declarations. A resolved
ref whose evidence baseline is missing remains in the full report with
`baselineStatus: "baseline_missing"`; this flag filters reference resolution,
not baseline qualification.

Scope follows the command contract: repeatable `--repo` names select configured
repositories or enabled members of an organization; omitted scope uses the
current directory. `--all`, pagination and positional arguments are unsupported.
Stored reporting needs no current repository folder. An explicitly named
disabled owner may be inspected; organization expansion selects enabled members
only. Names absent from settings receive `unknown_repository` even if the store
has rows for them.

Each `repositories[].result` contains `refs`, `count` and `unresolvedOnly`.
Each ref retains its dependency `id`, zero-based `occurrence`, exact `ref` spelling, `parsedRef`,
`rawLine`, `origin` and absolute `line`; a frontmatter occurrence has no line.
`parsedRef` strips spaces/tabs around a comment declaration and preserves a
frontmatter source string exactly. Equivalent aliases and duplicates may share
one edge and baseline, but every retained occurrence receives its own report
entry with the shared dependency ID and a distinct occurrence number.
`chunk` contains the stable chunk `id`, exact numeric `version` and portable
repository/root/path/name/address. `location` identifies the owning file
location and its disk/branch/stash kind and name. The command uses that location's
binding and chunk name, preserving distinct addresses even when locations share
one exact version. If the owning location is absent, `ownerLocationAvailable`
is false and the chunk's address/root/path/name are explicitly null; it never
substitutes another location.

`state`, `fault`, `resolutionFault`, `resolvedAddress`, `sourceState` and
`baselineStatus` describe the stored observation. The public fault names follow
the MYC-2 interface: `not_a_ref`, `not_found`, `ambiguous_path`, `ambiguous_title`,
`unknown_repository` and `disabled_repository`. `resolutionFault` retains the
more specific internal reason, such as `missing_name`, `ineligible_index`,
`not_checked` or `owner_location_missing`. `candidates` contains up to 20
portable Place objects; `candidateCount` preserves the complete count.

The invocation reads all selected owners in one PostgreSQL-enforced read-only,
repeatable-read snapshot under the shared store-format guard. It performs no
retry, ingest, store repair, mutation-lock allocation, activity write or evidence
collection. Settings, table rows and sequences stay unchanged. Unknown selector
faults coexist with successful repository results and produce exit status 1;
shared store/format preflight failures produce one closed command error before
any repository report starts. Stored reference faults themselves are successful
report contents and do not change the exit status.

`tests/test_refs.py` proves the public JSON boundary, option/error behavior,
exact duplicate/malformed retention through both declaration batches and the
complete located dependency producer, fault candidates, missing-location
distinctions, partial scope replies, no writes or model/Git children, and one
committed snapshot during a concurrent update against configured disposable
stores. These reporting proofs complete no ingest or MYC-16.2 claim.

`DeclaredRefStore.retain(settings, file_location, declarations)` verifies a
`read_document_declarations` result against the complete bytes of that exact
located file. It attaches frontmatter sources to the first chunk and comments
to their parsed section, preserving every duplicate, original spelling, line
and origin. Invalid raw text, including NUL, has an exact hexadecimal UTF-8
representation; PostgreSQL's display projection cannot erase a malformed ref.
Known document metadata and file diagnostics are retained on the file location.

Ownership includes the file-location UUID. A disk and branch location can share
one exact chunk version while declaring different sources. Retaining one batch
removes only that location's omitted declared records; assertions and other
locations survive. Evidence release checks dependency, relation, Drift,
classification and verification owners before collecting unreferenced blobs.

`DeclaredRefStore.recheck(settings, repository=...)` retries every retained ref
owned by an enabled repository on each pass. This includes origin passes,
target passes and settings changes. It uses the shared typed resolver for
source selection and atomically updates current member edges and visible fault
rows for each owner. Missing, malformed, unknown, disabled, ambiguous and
index-only source declarations create no active member edge. A newly colliding
legacy path becomes ambiguous even if the ref formerly resolved. Up to 20
qualified ambiguity candidates and the complete candidate count are returned.
Previously resolved disabled targets lose only their declared edges; assertion
records remain separately owned.

The pass validates that each owning file location and dependant version still
exist together. An unavailable owning location reports `owner_location_missing`
and deactivates its current edges; later ingest decides location retirement.
`list(repository=..., faults_only=...)` returns retained spellings and faults
without writing or retrying. A pass reply exposes `checked`, `changed`, `refs`
and `faults`; an unchanged repeat performs no feature write.

A resolved current selection can still report `baseline_missing`. Resolution
does not establish a baseline. Initial pins use the existing guarded
`DiskPinObservation` and `EvidenceStore.pin` boundary, which rereads complete
current files and resolution under repository locks. File pins retain every
byte, including frontmatter; class-family pins retain ordered stable membership
and each member's exact hash. The same resolver requires one mutation dependant
or relation endpoint; a class endpoint selects its header, and a whole file or
index-only endpoint is refused. Index-only selections remain available for
permitted reads.

Rechecks preserve `baseline_owner` and never repin after a source edit,
enablement change, disappearance or restoration. A ref that formerly resolved
reports `source_removed` when its enabled current source disappears; a ref that
never resolved remains unresolved. The original immutable baseline and audit
declaration remain intact. The complete ingest/dependency producer supplies
initial pin/reconciliation transactions, cycle checks, away/deleted decisions
and public command replies; the reference pass itself only rechecks retained refs.

`bind_disk_file(connection, settings, repository, captured)` rereads all
physical aliases under the repository guard before persisting complete file
bytes. Overlapping roots share a file ID. First discovery chooses the most
specific resolved containing root, with `artifact` winning equal-root ties.
An existing primary remains while its alias still reaches the file. Different
physical files with equal bytes or relative paths remain distinct.

An explicit `recognized_move` names an existing file ID and must reproduce its
recorded physical identity. A move preserves that file's IDs and exact-version
rows, records old qualified aliases as move evidence and updates the current
canonical place. Previously resolved refs can follow their retained anchor only
when the old path is absent and recorded move evidence identifies that source.
A new ref receives ordinary resolution. A reused old path, ambiguity or an
ineligible repository cannot be overridden by the old anchor. Branch/stash
locations with legacy inherited bindings retain their own original addresses
when disk's binding changes.

An atomic save that changes the inode at an established path returns
`invalid_input` for the file identity reconciler. This narrow binding API does
not infer an edit or merge from equal paths/content, and does not implement
Git-recognized moves across physical identities. The complete-file handoff below
handles those cases; this binding API assigns no new chunk IDs and carries no
old chunk location into changed bytes.

`DiskCaptureStore.apply(settings, manifest, recognized_moves=...)` consumes a
complete `capture_repository` result. Under the repository pass guard it reads
one stored identity catalog and repeats the actual scanner before preparation
and immediately before writes. Equality includes the parsed inputs, not only
the manifest hash; only a caller's primary choice within proven aliases and
resulting file order are normalized, so a previous stable primary remains valid.
Changed bytes, enumeration, roots, Git inventories, failed
parses or an unconfirmed empty on-disk corpus refuse publication and retirement.

The handoff persists complete file bytes, stable chunk decisions, exact versions
and location metadata in one transaction for the full disk capture. It returns
each persisted chunk UUID/version alongside the explicit pin decision. Located
names and spans can change while an identical exact version remains shared.
Unchanged repeated captures make no feature writes and no activity entry.

Recorded resolved root identities and absolute file paths distinguish an atomic
save at an established physical place from a retargeted root. An atomic save
preserves file/chunk identity while replacing exact versions as appropriate.
Physical identities are reserved across the complete capture before applying
same-place continuity, so moving the old file and reusing its original path
creates distinct current identities. Root reconfiguration preserves an ID when
it demonstrably reaches the same physical file; a different file with equal
bytes/path receives a new ID.

`GitFileMove` supplies an existing file/version UUID, full before/after commit
IDs and qualified source/destination aliases. The boundary checks both local
commit objects, both complete blobs, the old physical path's absence and an
explicit `git diff -M` rename record. It repeats those checks before publication
and retains the commit/name/version proof with the location. A copy/unlink
without that evidence receives a new ID. An old name that is reused always goes
through ordinary resolution, including its ambiguity and name faults.

Complete located publication also derives checked cross-path correspondences
from local ancestor/descendant commits, explicit Git rename records and both
complete blobs. It retains the physical checkout/root scope and repeats the
proof before writes. A unique direct pair can recognize a committed disk move
without a supplied `GitFileMove`; branch/stash binding can follow proven rename
chains. Copied files and unrelated histories keep distinct identities. A reused
old physical path, conflicting IDs or unavailable proof refuses publication.
This does not complete dependency identity policy or unlocated-version collection.

Absent disk locations are retired in the same transaction, while branch/stash
locations retain their own original bindings. The unreleased format-1 schema no
longer makes global `(repository, root, path)` columns unique: distinct retained
locations may legitimately hold distinct physical file IDs at that address.
The checked complete capture establishes one disk owner per qualified alias;
the location-aware resolver still refuses any ambiguous catalog.

An optional `file_handoff(connection, applied_file)` runs after the exact file,
chunk/version and disk-location rows exist, inside the same transaction. It
provides a concrete apply boundary for a dependency producer: no nested
transaction, independent commit or provider call is allowed. Any handoff or
audit failure rolls back the entire capture. Optional `activity=active_audit`
adds actual file and persisted identity details through that same transaction;
`reply_counts(repository, local_counts)` supplies cumulative command counts and
must be pure. The caller finishes the activity with its final reply counts.

This disk handoff is one part of complete public ingest. The separate
[located handoff](capture.md#complete-located-publication) publishes complete
disk/branch/stash identity locations. Its dependency producer applies
prospective graph checks, baseline capture/inheritance and current edge
reconciliation, followed by guarded unlocated file/version/chunk/evidence
collection. Retired unlocated rows are excluded from current resolution and
supply no guessed identity. MYC-16.2 has named configured-store proofs for
aliases, stable primaries, physical/Git moves, distinct identities, root
reconfiguration and the disk-store handoff. SYL-119 composes these boundaries
through the public `ingest` command.

Optional `recheck(..., activity=active_audit, reply_counts=callback)` commits
actual dependency/fault/edge writes and their ingest activity together on the
same connection. The pure callback receives `(owner, local_counts)` and returns
the producer's cumulative command counts. It must have no side effects because
the transaction can roll back. Final counts, including no-op observations, are
supplied through `activity.finish(counts=...)`. Dependency-only passes fabricate
no file or identity details, and a no-op creates no activity entry.

The configured disposable-store proofs are in `tests/test_declared_refs.py`;
native producer/audit composition is in `tests/test_activity_store.py`. Existing
declaration/address unit proofs and location-aware resolver proofs remain in
`tests/test_source_refs.py` and `tests/test_resolver.py`. Complete disk handoff,
atomic save, checked Git rename, root reconfiguration, retirement, exact code
rename, no-op and audit/handoff rollback proofs are in
`tests/test_disk_reconciliation.py`.

## Caller-transaction declaration handoff

`retain_in_transaction` parses the prospective exact file/location rows and
`recheck_in_transaction` applies retained faults, current bindings and expanded
source-version edges in the caller's complete publication transaction. Surviving
declaration IDs refresh occurrence metadata (including shifted absolute lines)
without changing their baseline ownership or current resolution. They
allocate no guards, open no savepoints and commit no prefix. The caller holds
`checked_store` and every configured repository's pass/removal guards before
opening the transaction; the adapters check the actual granted locks on that
connection. `SourceResolver.from_transaction` reads that same prospective
catalog, including the selected branch/stash location, without a disk fallback.

The producer can then capture initial exact baselines through the evidence
transaction adapter. Configured fixtures verify that files, declarations,
edges, evidence and activity become visible together; frontmatter variants
sharing one exact dependant version retain separate location-owned pins. A
source-only change updates current edges while leaving each baseline untouched.
An unchanged capture can run a separate explicit reference/activity transaction
to retry refs; the publication callback itself still skips no-op captures.

This basic retention adapter still refuses pinned replacement/removal. The
separate `DependencyApplicationStore` matches logical declarations independently
of spelling and order, translates version-specific dependency IDs and applies
the identity-authorized inheritance, repin or withdrawal policy with current
edges, faults and located roles. Duplicate aliases retain all occurrences while
owning one same-kind dependency. The original manifest and audit declaration
remain exact; the current spelling and recognized binding are separate state.

`LocatedDependencyProducer` supplies the actual capture/settings rereader and
chooses policy from each persisted identity decision. Its optional complete
capture collection runs after policy application. See [reconciliation.md](reconciliation.md)
and [identity.md](identity.md#guarded-unlocated-collection). These private producers
have configured store proofs and are composed by public ingest.
Automatic mechanical detection follows complete publication as documented
in [reconciliation.md](reconciliation.md). The guarded
`derive` command now has exact assertion-only ownership, complete fresh source
and dependant guards and named configured checks in `tests/test_derive.py`.
These APIs and their public consumers share the guarded declaration/resolver
boundary.

## Entity URIs (MYC-17)

`parse_entity_uri` and `format_entity_uri` read and write the glossary's
Entity URI, `[<tag>:<uuid>:<title-base64>]` or `[<repo>:<tag>:<uuid>:<title>]`;
`any` as the repo code means none, the UUID is lowercased, and the title is a
display snapshot that takes no part in identity. The shared resolver accepts a
URI wherever it accepts an address: it looks the UUID up among the current
located chunks, uses the kind tag only as a check (`entity_kind_mismatch`),
refuses a `cht` URI as `ineligible_entity`, reports a UUID it does not hold as
`missing_entity`, and returns the typed selection `req` or `dec` with one
member whose place is the file's address with the human id as the name. A
`req` or `dec` chunk keeps its comparison as exact text (`code_text`), so pins
and evidence treat the row like a code chunk. A sources comment names an entity
by that address; the URI form in declarations, `derive`, `relate` and `confirm`
is owned by the open justification Beat SYL-260.
