# Whole-file identity and exact located versions

`reconcile_file(incoming, known)` is a pure internal API that plans stable chunk
identity and exact text-version decisions for one already-resolved file. It
accepts immutable tuples of `ChunkInput` and `KnownChunk` and returns a
`FileIdentityPlan`. It allocates no persistent identifiers, accesses no store,
changes no location, copies no evidence and makes no provider call. The private
`DiskCaptureStore` consumes this plan in a checked disk transaction, and the
private `LocatedCaptureStore` publishes complete disk/branch/stash identity
locations atomically. The complete located dependency producer applies identity-selected evidence
and guarded unlocated collection in that transaction. The public `ingest` command composes those APIs; see the
[reconciliation guide](reconciliation.md#complete-public-ingest).

`ChunkInput.document(MarkdownChunk)` reproduces and validates the existing
document body/title comparison records and exact stored-text hash. Document body
matching uses NFKC plus collapsed Unicode whitespace; the heading is excluded.
`ChunkInput.code(CodeChunk)` uses the symbol name within the file and SHA-256 of
the complete exact UTF-8 code text. The file path is separate file metadata.
Names are exact strings; a normalized title hash never substitutes for a name.
Unsupported comparison revisions or inconsistent hashes are visible faults.

The matcher has two rounds over the entire file:

1. Reserve every current name match first. Among the remaining inputs and known
   identities, match historical names without displacing a current reservation.
2. Match remaining nonempty body/content comparisons. Empty and whitespace-only
   bodies never take an identity through content matching.

Each phase uses deterministic maximum one-to-one assignment. Input names and
stable chunk IDs break ties; the current version precedes other numeric version
IDs. Source order is retained in the returned decisions. Changing the order of
known storage rows or retained versions does not decide identity. This prevents
a newly added or renamed section from consuming a later section's name match.

`KnownChunk` names a stable identity, its current version and all supplied exact
retained versions. Each `KnownVersion` has a positive version ID and its exact
`ChunkInput`, plus optional immutable `historical_names`. These located aliases
let identical child-section text retain its names under different parent paths
on disk, branches and stashes without duplicating a version ID or its bytes.
Aliases must be nonempty exact UTF-8 labels without NUL; duplicates are removed
and the tuple is sorted by UTF-8 bytes, with no Unicode normalization. The
current-name phase still uses only `known.current.chunk.name`; aliases take part
only in the historical-name phase after all current names have been reserved.
The disk handoff supplies these aliases from recorded locations.
Every exact text has one version within that identity. The plan
returns `unchanged`, `edited`, `renamed` or `new` decisions, the matching phase,
reference version and either an existing version ID or a pending new version.
Normalized-equivalent body edits can be `unchanged` for identity comparison while
still requiring a different exact text version.

Pin decisions are explicit:

- `restore_existing`: byte-identical known text reuses that exact version and its
  own existing pins. It never adopts the current disk version's later pins.
- `inherit_existing`: new exact text with an applicable normalized-equivalent
  body or recognized rename carries the explicitly selected reference version's
  pins. A substantive edit against a current-name reference does not adopt an
  unrelated archive's pin merely because that older body resembles it. The
  evidence layer must preserve the original source snapshots and audit data.
- `requires_authorized_capture`: a new identity or substantive content edit does
  not authorize a pin merely by producing this plan. A later checked transaction
  must establish the accepted MYC-D12 or other explicit capture trigger.

`reuse_vectors` is true only for byte-identical known text. A heading rename or
whitespace edit that changes the stored bytes creates a new exact version and
does not borrow another version's vectors. A changed heading-path/name metadata
with identical complete stored text can reuse that version. The API exposes an
eligibility decision; it does not establish that vector rows exist.

`removed` means absent from this one file input. It never authorizes deleting
rows still present in another disk, local branch or stash location. A future
full ingest caller must consume complete read-only capture in disk/branch/stash order,
hold the checked store/operation guards, apply each file atomically and reconcile
all locations before deletion. It must also connect the explicit inheritance
decision to the evidence layer and preserve dependant-owned missing-source data.

The owner accepted MYC-D38 on 9 October 2026. A separately versioned
`parsed-declaration-name-v1` identity key erases only the parser-located
identifier, keeping the signature, body, comments, whitespace and all other
bytes exact. Language and structural kind are bound into the key, with
length-prefixed components. Python and tree-sitter declarations carry the
original UTF-8 name span; a chunk without a parsed declaration uses its
complete-code comparison. All name matches remain reserved before round two.

A name-only rename preserves identity and inherits the selected version's pins,
but different source bytes create a new exact version and reuse no vectors.
Complete-code comparison hashes and dependency evidence never use this
projection. Unit proofs cover actual Python/TypeScript/JavaScript functions,
methods, Unicode names, CR line endings, changed signatures/bodies and shared
document/code name-reservation rules. The disk handoff persists exact versions
and located metadata and verifies physical/local-Git file moves. The located
handoff additionally persists captured local branches and stashes and restores
their exact identities/own existing pins. Configured-store proofs establish the scoped identity/exact-version API,
including checked moves, restored/inherited own pins, exact vector reuse and
surviving dependant-owned evidence after source removal. Public ingest consumes these APIs in a complete guarded pass.

## Transactional ingest boundary

A later ingest loader must read all retained exact versions and located name
projections in one snapshot. The current source resolver supplies one selected
location, rather than the complete history needed by this matcher. Preserve
`LocationId.record()` including checkout anchor; a bare branch name cannot
distinguish independent configured roots. Process the capture's disk, branch and
stash ordering, and bind physical aliases before deciding file moves.

`DiskCaptureStore` reads exact chunk history and located names in one checked
snapshot, reserves physical file identities before same-place atomic-save
continuity, and publishes a full disk capture atomically. Its transaction-scoped
`file_handoff` receives each persisted UUID/version and explicit plan after the
identity rows exist. Existing branch/stash rows are preserved. It neither writes
new Git locations nor captures/inherits evidence, and leaves unlocated rows for
the later collection boundary. See [source-refs.md](source-refs.md) for the exact
guards and checked Git-move contract.

`LocatedCaptureStore` supplies the subsequent complete located publication seam.
It loads disk and Git file bindings together, preserves independent checkout
anchors and physical root scopes, and reconciles each location in capture order.
Newly persisted versions participate in later locations' matching within the
same transaction. A branch-only file restored at its checked natural place uses
its existing identifier; identical text within that identity restores its own
exact version and `restore_existing` pin decision. Equal bytes in independent
files or root retargets never establish identity. Located parent-path/name
projections let one exact child version retain its distinct names in several
trees. Automatic cross-path correspondence now requires Git's recorded rename,
local commit ancestry, checked physical checkout/root scopes and both complete
regular blobs. Captured and retained Git snapshots can establish the proof; an
exact placed disk input can anchor to one of those snapshots. Copied files,
unrelated histories and equal content alone never establish identity. A disk
move also verifies the exact old version and the old physical path's absence;
ambiguous evidence or a reused old physical path refuses the complete publication.
The proof inventory is checked again inside the publication transaction. Exact
version and pin decisions still follow the whole-file matcher independently of
the move evidence: an edited rename never borrows another version's bytes or
vectors, and a substantive edit still requires an authorized baseline capture.

The entire fresh capture/catalog/root scope is checked again before publication.
Absent locations retire after all captured locations publish, while unlocated
versions/chunks and their pins are retained unless the guarded collection
producer explicitly applies their accepted removal policy.
Changed captures can hand the complete persisted prospective catalog to a
transaction-scoped batch callback, and any callback/audit failure rolls back the
whole publication. No-op captures rewrite no catalog row and invoke no callback.
This has configured store proofs but remains a partial ingest implementation.

Build a finite prospective catalog before writes. For a dependency-connected
component, insert its exact file/chunk/version rows first, then bind sources and
owned evidence within the same transaction after validating the complete proposed
graph. The prospective catalog resolves cross-file references without inventing
stored version identifiers; self-dependencies and cycles must be refused before
any changes commit. Each file must remain all-or-nothing. The evidence layer's
`pin_in_transaction` and `inherit_in_transaction` now compose checked baseline
writes with identity/activity publication. Their `checked_input_guard` begins
before the caller's transaction and rechecks fresh inputs before application.
The private dependency application executor and complete located producer now
join those boundaries. They match logical declarations, retain each location's
own exact-version pins, apply inherited or authorized captured baselines and
update current faults, expanded edges and located roles. A guarded complete
batch replaces pending declarations' authority before cycle checks, then checks
the full persisted graph before leaving the caller transaction. A valid
declaration reversal cannot depend on file processing order. Public command
orchestration and full acceptance remain unfinished.

Restore a known version's own dependencies, inherit from the plan's selected
`pin_version`, and capture a new baseline only under an explicit accepted trigger.
Missing or disabled current sources do not prevent inheriting a surviving owned
baseline. Reconcile natural faults and current edges separately from that pin.
Defer absent-location/version/chunk deletion until the complete capture has been
validated against the previous nonempty disk corpora and any required confirmation.
File-local `removed` decisions alone cannot authorize global deletion.

## Guarded unlocated collection

The private `CollectionStore.collect_in_transaction(settings, manifest)` can
join the complete located publication callback after all dependency evidence
has been applied. It opens no transaction, savepoint or guard. The active caller
must hold its connection's checked structure and repository pass/removal guards,
including any downstream repository whose resolved source edges disappear.

The collector rereads the complete disk, local branch and stash capture and
checks its published inventory, exact full files, parsed chunk locations,
physical root scopes and disk file identities before deleting. An incomplete,
changed or unpublished capture refuses the transaction. Every located version
survives, with its own pins, plans, parts and vectors. Only unlocated file-backed
versions are deleted; their empty stable chunk identities and unused file rows
then disappear. Synthetic index-only text remains its generator's responsibility.

Deleting a source version removes current resolved edges while surviving
dependants retain their existing records and owner-scoped exact evidence. A dead
dependant releases only the owners of its removed records; surviving history or
invocation references still protect the blobs. Original complete file versions
named by retained code baselines for a surviving stable identity remain private
and unlocated, so a later parser-verified name rename can reproduce its original
file context. These file bytes have no search location or vector.

Configured PostgreSQL fixtures cover branch/stash ownership, source and dependant
deletion, downstream guards, complete rollback, busy rows, changed physical
files, withdrawal/history/lease retention and subsequent code rename inheritance.
Its surviving dependant-owned deletion evidence participates in the scoped
exact-version acceptance proofs. Complete public ingest includes collection and
detection after deletion. Drift closure/history pruning retains protected evidence.
Public repository removal uses the same owner release and collection boundaries
under the exclusive removal guard; see the [store guide](store.md).
