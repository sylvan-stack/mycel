# Exact dependency evidence

The private `_evidence` API separates comparison identity from exact retained
bytes. It creates canonical immutable baseline manifests and stores complete
source/dependant snapshots in their dependant repository. Configured-store
acceptance verifies the scoped capture and inheritance APIs. Located ingest,
public confirmation and the generated publication hook now consume those
retained exact inputs. Public summary build/regeneration/removal and `classify`
compose their own guarded request, response and retained-history consumers.

`ComparisonRecord` records the hash kind, algorithm revision and, for document
body/title comparisons, the Unicode database version. Body and title use the
Markdown parser's recorded NFKC/Unicode-whitespace rule independently. Code
comparison hashes exact UTF-8 text, file comparison hashes every original byte,
and exact snapshots always hash the complete original bytes. An unsupported
revision is `unsupported_comparison`; no current parser or normalization rule
repairs or replaces it. Missing recorded body/title comparison or body extraction
also refuses capture. Body comparison never becomes a title pin.

The resolver supplies immutable stored comparisons, exact complete chunk text,
the parsed title and a checked relative `body_span`. Evidence retains a private
`comparisonSpan` descriptor so every document-body comparison can be reproduced
from the complete retained snapshot without reparsing Markdown. Full-file
`fileHash` and byte `span` record extraction guards. They are distinct from the
body projection and are not normalized. Private `selectionComparison` records
the selected hash's kind/revision, including the family algorithm; no public
command or store schema is changed by these extraction fields.

`canonical_json` emits UTF-8 JSON with sorted Unicode keys, literal Unicode,
ordered arrays and minimal JSON escapes/separators. It rejects floating-point
values, nontext object keys, cyclic data and invalid Unicode. A manifest's ID is
SHA-256 of its canonical payload without its own ID. Stored manifest bytes are
that same payload, allowing the store's exact-byte checksum to verify it.

`capture_baseline` preserves the dependant's stable identifier/exact version,
its complete text, the literal source declaration, portable resolved place,
selected kind, complete source bytes, ordered members and capture location/time.
A file selection stores one complete file snapshot, including frontmatter and
undecodable bytes. A chunk selects one complete stored chunk. A family stores
its header and ordered member snapshots. Canonical places and comparison
records determine family comparison; internal member identifiers remain audit
data. Duplicate places/identifiers, mismatching selection/member places or
kinds, and inconsistent pinned hashes are refused.

`PinInputs` binds the dependant and complete files, current source selection,
original raw declaration/resolution, complete resolver catalog, immutable
settings, capture location and additional observation guards. Both dependant
and source must resolve to those exact inputs. A later legacy path collision,
disabled source or invalid/unresolved declaration cannot be confirmed by
substituting its qualified address. Branch/stash consumers must supply the
explicit retained location, its commit and location observation identity;
another branch's bytes are not a supported reread adapter.

`checked_input_guard(connection, expected, reread)` acquires a checked shared
structure guard and nonblocking pass/removal guards for every involved
repository in sorted order. The callback uses the one validated invocation
settings snapshot and freshly reads indexed versions, current disk or exact retained-location files and full-catalog
resolution. Returning a previously captured object is only a test seam, not a
production observation adapter. Missing/invalid callback output or changed
settings, complete file hashes, member identities, exact versions, declaration,
body extraction or extra guards returns `changed_since_ingest` with qualified
affected addresses before any evidence write. The [disk observation adapter](pin-observation.md)
supplies real disk/catalog rereads; the ingest/mutation consumer must still establish
MYC-D12 authorization. Complete located publication supplies retained branch/stash
capture observations through the producer described below. Public `confirm`
uses the same guarded direct-pin policy and independent verification evidence.

`EvidenceStore.pin` accepts explicit initial-resolution, dependant-edit or
owner-confirmation authorization and compares the existing baseline owner.
Inside one guarded atomic transaction it rechecks and locks exact file/chunk
rows, stores all snapshots and the canonical manifest, creates owning
references and binds the version-specific dependency. Chunk rows must belong to
the expected repository and file. Snapshot/manifest conflicts are checked rather
than overwritten. SQL errors are sanitized, a busy lock fails without waiting,
and any capture/binding failure rolls the complete change back. An explicit
confirmation releases the replaced live baseline owner only when no dependency,
relation, verification, Drift, classification work or invocation retains it.
Collection occurs only in this guarded writer transaction and removes only
blobs/manifests with no owning reference.

`inherit_baseline` and `EvidenceStore.inherit_pin` preserve original source
snapshots, member comparisons, selected pin, declaration and capture audit when
the identity reconciler authorizes a recognized rename or normalized-equivalent
edit. They verify stable dependant identity and equivalent recorded comparison,
then attach the new exact dependant version/bytes to its own immutable manifest.
An authorized code name-only rename under MYC-D38 may change the complete-code
comparison. In that case inheritance reparses the complete original file selected
by the baseline's exact file hash and extraction span, and the fresh complete
dependant file. Both parsed chunks must reproduce the recorded names, spans and
bytes and have the same conservative versioned declaration-name projection.
Changed signatures, bodies, comments or other bytes refuse inheritance; missing
original file bytes cannot be replaced by current text. The new manifest retains
the new complete-code comparison and exact bytes alongside the identical old
source pin. The store locks the original complete file without waiting before
publication. Document and normalized-equivalent inheritance keep their existing
strict comparison check.
Inheritance verifies the old baseline owner's repository, kind and dependency/
manifest identity, its complete ordered blob references, and the previous
dependant version's exact bytes, stable identifier and recorded pin comparison.
One read snapshot captures those bindings; nonblocking row locks recheck them,
the old manifest and every old snapshot's complete metadata/bytes inside the
writing transaction. The former file binding need not survive a
recognized move, and deleted or disabled source rows are never reconstructed.
`InheritanceInputs` guards only the fresh dependant and current resolution/fault
metadata; it does not require a live source selection. The disk adapter's
`observe_inheritance`/`reread_inheritance` supplies that real observation. Owned
retention never grants a caller permission to expose disabled source evidence.
They never capture today's source as an inherited baseline. Old branch/stash
version pins retain their own owners. Complete ingest applies location and
baseline reconciliation, while `derive`, relations, generated publication and
classification compose separate guarded evidence consumers.

The private `pin_in_transaction` and `inherit_in_transaction` apply boundaries
accept the active token from `checked_input_guard`. Acquire and reread that
guard before opening the caller's atomic transaction. Insert the prospective
file/chunk/version rows, then apply evidence with that token in the same
transaction as dependencies, graph changes and activity. These methods neither
allocate guards nor begin, commit or nest a transaction. They refuse idle,
aborted, foreign-connection and expired tokens before writing. Exact stored
versions and the baseline owner are rechecked; inheritance locks and verifies
the complete previous owner, references, version, manifest and snapshots.
An error must escape the caller transaction so its whole change rolls back.
The existing `pin` and `inherit_pin` wrappers continue to own their complete
transactions. Complete ingest composes current-binding/declaration updates and
location-owned dependency records through the guarded producer described in the
[reconciliation guide](reconciliation.md#complete-public-ingest).

`read_snapshot` verifies retained metadata, byte count and SHA-256 before use.
`read_baseline` also validates canonical manifest bytes, selected membership and
all required snapshots/comparison projections. Missing data is
`baseline_missing`; damaged data is `snapshot_corrupt`. A text-only use of
non-UTF-8 bytes is `insufficient_evidence`, with no replacement decoding; a
finite whole-input limit yields `input_too_large`. There is no provider call in
this module. Callers must enforce current repository visibility before exposing
private evidence or building a paid request.

`reconstruct` accepts only exact candidate blobs or complete files matching the
recorded full-file hash/extraction span. A newer file with identical selected
text but a different full-file guard is refused. `restore_snapshot` additionally
requires an existing owner reference and restores only matching bytes; it
changes no manifest, dependency owner or pin. A corrupt existing blob is not
overwritten. No missing baseline is silently rebuilt from current text.

Evidence rows have no searchable chunk, location, vector or source-row ownership
foreign key. Cross-repository source copies belong to the dependant repository
and survive source deletion through explicit surviving references. Reporting
performs no collection. The ordinary native tests use seeded exact versions and
the gate's default disposable product-store fixture, separate from scripted SQL
seams and from owner-configured acceptance/Build claims. Pure comparison checks
declare MYC-16.4; seam checks declare only MYC-13.15. No owner credential,
provider endpoint or live database is accessed by those offline checks.

## Prospective input guard

`checked_transaction_input_guard` joins an already-open native publication
transaction. It first checks that its own connection actually holds the shared
structure guard and every configured repository's pass/removal guards, then
compares a fresh observation with the expected exact input identity. It opens
no savepoint and allocates no lock. The token expires on context exit and the
existing transaction apply methods still check connection, transaction state,
exact stored file/version bytes and owner identity.

The rereader must verify actual disk or exact retained captures, the invocation
settings and the prospective `SourceResolver.from_transaction` catalog. A cached
object remains only a test seam. Configured initial-capture fixtures reread the
real manifest and complete selected bytes; a disk change before pinning or a
producer/audit exception rolls back the complete publication. The separate
dependency executor now supplies identity-selected inheritance, current
declaration/binding updates, authorized repin and withdrawal application.
`LocatedDependencyProducer` rereads actual source/dependant captures and settings,
including enabled foreign repositories and physically recreated missing paths;
the publication checks its whole capture again after the last producer.
Public consumers retain exact evidence through confirmation, classification
and summary publication/regeneration. Installed working-Build qualification is owned by SYL-148.

## Collection application

`CollectionStore.release_baseline_owner_in_transaction(owner, repository)`
releases one explicitly selected baseline owner only after no dependency,
relation, verification, Drift, classification work or invocation retains it.
`collect_evidence_in_transaction(repository)` then removes only snapshots and
manifests with no owning reference in that repository. Both require the caller's
active guarded transaction and allocate no lock or savepoint. They supply a
release/withdrawal apply boundary; they do not authorize withdrawing a source.

The collector's complete-capture boundary is described in
[identity.md](identity.md#guarded-unlocated-collection). It may delete a source's
searchable rows and vectors while leaving exact copies owned by another
repository's surviving dependant. It also keeps original complete file versions
needed to verify a surviving code baseline's later name-only rename. Collection
never substitutes current file text for those bytes. A later graph, evidence or
activity failure must escape the caller transaction so all deletion and owner
release rolls back with publication.

`DriftHistoryStore` retains independent closed exact-input bundles and bounds
eligible closed history to the newest 1,000 records per owner repository. It
preserves live work, current suppression, baseline and verification references,
and in-flight request leases. Superseded request evidence transfers to its
historical owner before the live owner releases its references. Late obsolete
attempts attach to that exact bundle; eligible pruning removes its record,
metadata references and wholly unreferenced blobs in the same transaction.
These operations require the caller's connection-owned structure/pass/removal
guards and open writing transaction. Reports and activity-only deletion never
collect evidence.

`CollectionStore.remove_repository_in_transaction` provides the guarded release
handoff for the public repository-removal command. It requires the owner's
exclusive removal guard and all affected repository pass guards, refuses live
invocations or evidence leases, and releases only the removed repository's
ownership. Other repositories retain their dependant-owned copies and natural
dependency records. Public `repos remove` binds current settings, reports exact
removed counts and protects foreign edge owners before cascading source edges.
Surviving dependant reads project the missing source from retained natural places
and pins. A deletion-transaction or attached-audit failure rolls back the whole
removal; a final audit-close failure preserves the already committed reply counts.

Successful generated publication creates an independent permanent `generated`
evidence owner with both original request and completed response manifests plus
all exact prompt, request, full/sent member and response snapshots. Every request
member has its own generated dependency pointing to that complete owner.
Owner validation binds the complete ordered membership to produced dependant
bytes and compatible summary state; source removal and expired request leases
do not release published evidence. Same-response regeneration renews generated
pins and releases a superseded owner only when no other owner-bearing row
retains it. Declared/asserted baselines and verification history stay independent.

`GenerationEvidenceStore.retain_in_transaction` and
`retain_response_in_transaction` adopt already prepared request/response bytes
inside the caller's checked guarded transaction, with no command or commit.
They supplement the existing short-commit `retain`/`retain_response` methods.
The public summary publisher owns protected hidden staging before external calls
and releases temporary invocation leases only after successful publication.
See [generated.md](generated.md) for the successful publication contract.
