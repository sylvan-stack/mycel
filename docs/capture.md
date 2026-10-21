# Read-only corpus capture

The internal `capture_repository(snapshot, repository, previous=..., cancelled=...)`
API prepares complete source inputs for later ingest. It accepts one enabled
repository from the immutable settings/scope snapshot and returns an immutable
`CaptureManifest`. It never accesses the store, acquires provider credentials,
changes settings, checks out a branch, fetches or modifies repository metadata.
The private `DiskCaptureStore` handoff consumes the disk inputs. The private
`LocatedCaptureStore` now publishes disk, local-branch and stash identity rows
together in a checked transaction. The complete located dependency producer composes declaration/evidence
application and guarded unlocated-version collection in that transaction.
The product `ingest` CLI handler composes complete capture, publication,
dependency reconciliation, Detection and collection under scoped guards.

The manifest orders disk input first, local branches next and stashes last.
Branch records retain the full local ref and commit; remote branches are omitted.
A stash is identified by its commit, so shifting list numbers do not change its
identity. Its working-tree tree and optional third-parent untracked tree are
combined, without substituting current disk bytes. Separate checkouts backing
the two roots retain distinct portable location scopes. SHA-1 and SHA-256 Git
object IDs are supported. Replacement refs are disabled by the shared safe Git
boundary so an unchanged commit ID cannot silently acquire substitute content.

Both configured roots supply documents according to the configured endings.
Code is selected only under the code root and its optional source subfolders;
those restrictions do not exclude checkout documents. The same directory skip
list and hierarchical `.gitignore` matching apply to every location. Ignore
rules come from that location's own bytes, including ancestor rules when a root
is inside a checkout. Directory exclusions cannot be undone by a child rule.
Regular `.gitignore` files still supply rules when their own filename is ignored;
an excluded ancestor directory prevents descent. Git wildcards count bytes,
including UTF-8 filenames, and bracket expressions preserve Git's POSIX classes,
literal escapes and inverted-range behavior. The explicit simple pathspec backend
avoids optional ambient matching engines.

Each actual checkout contributes its effective local `core.ignorecase` value
through the shared boundary's one permitted configuration read. An absent value
uses Git's default false. Matching folds ASCII bytes according to Git's segment
rules and preserves other bytes. The value participates in the cache fingerprint
and is checked again before completion; unsupported or changed policy makes the
capture visibly incomplete.

Configured root symlinks resolve once. File and directory symlinks below roots,
Git symlink blobs, gitlinks and special disk files are excluded. Disk reads use
no-follow descriptors, retain all bytes and compare file/directory observations.
Final disk observations and local-ref inventories detect changes during capture.
Common skipped names match folders and ancestors, never an equally named regular
file. Git's own metadata directory is excluded from corpus traversal.

Every captured file retains exact original bytes, SHA-256, document/code origin,
its portable primary root/path and all discovered aliases. Overlapping roots
capture a physical file once in a location; identical bytes in distinct files do
not merge them. A previous primary remains primary while it still reaches that
file. New discoveries choose the more specific root, with artifact winning an
equal-root tie. The Markdown/code parsers receive exact source bytes when splitting is needed.
Undecodable source retains its bytes and a localized failure; no old rows may be
removed on that basis.

The store handoffs provide `capture(settings, repository)` and accept a literal
repository name in `apply(settings, repository)`. These paths load committed
lossless parser records from exact file-location history, so separate invocations
reuse unchanged Markdown and code without splitting again. The private inert
JSON record binds complete file bytes and the policy/parser fingerprint; missing,
corrupt or incompatible records fall back to a fresh parse. Legacy rows need no
schema migration. Git reuse additionally requires a complete retained inventory
with the same commit, recorded trees and file count.

Every disk candidate is read again before unchanged parsing is reused. Immutable
Git locations can reuse a previous complete capture only under the same commit
and root/policy/parser fingerprint. That fingerprint includes parser source,
pinned parser dependencies and interpreter/Unicode behavior. Cache flags do not
change manifest identity. `canonical_bytes()` is versioned canonical JSON and
`manifest_hash` is its SHA-256; this scan format is separate from the MYC-16
baseline/request manifest format.

`delta(previous)` exposes unchanged, changed, new and safely removed file inputs
and added/removed locations. It updates no persistent hash. A changed parser or
scan policy requests fresh reconciliation even when source bytes are identical.
`complete` records successful acquisition; `deletion_safe` additionally requires
every captured source to parse. Incomplete enumeration, failed/short reads,
invalid portable paths, changed observations or parse failures suppress all
removed-file and removed-location outputs. `require_safe_reconciliation()` also
refuses an unexpectedly empty on-disk corpus unless explicitly confirmed. A
private disk handoff establishes the actual previous disk rows and refuses an
unconfirmed empty corpus; it repeats the complete actual capture before
publishing file/hash/chunk/location decisions together. These memory guards
alone cannot prove that behavior.

Git metadata uses the safe child's ordinary 1 MiB output cap. Oversized metadata
produces a visible incomplete capture, never a truncated successful inventory.
Blob reads use their exact finite object byte count as the output cap and have
the same finite 10-second deadline and cancellation as other Git reads. Large
logical chunks are retained whole; provider limits have no role in capture.
Private temporary disk/Git unit fixtures exercise these rules without a store
or quota. Configured disposable-store handoff proofs now cover unchanged disk
persistence, empty-corpus refusal, stable file/chunk IDs, atomic saves, checked
Git moves and exact located metadata in `tests/test_disk_reconciliation.py`.
Configured disposable-store proofs in `tests/test_located_reconciliation.py`
also exercise actual branch/stash persistence, branch-only file restoration,
exact versions with their own existing pins, independent checkout scopes,
location retirement, no-op preservation and callback/activity rollback. These
partial proofs do not qualify complete ingest requirements.

## Complete located publication

`LocatedCaptureStore.apply(settings, manifest, ...)` by default rechecks the
actual complete capture and stored catalog under the repository pass guard.
Public ingest selects `publish_capture=True`: it publishes the captured input
and reports later disk/Git changes under `changedDuringPass`, as described in
the [reconciliation guide](reconciliation.md#complete-public-ingest). It publishes disk
first, then the capture's sorted local branches and commit-named stashes. Every
file and its chunks retain exact bytes, one stable file/chunk identity across
checked locations and one version per identical stored text. Located names,
aliases and extraction spans remain separate from the exact version's metadata.
Each location records `LocationId.record()`, its full commit and policy hash.
`location_key` supplies the resolver's unambiguous retained selector, including
the `code`/`artifact` checkout anchor; matching branch names in two independent
configured checkouts never select or merge each other's files.

Physical disk identity and same-place atomic-save rules remain authoritative
for disk continuity. A branch-only file can return to disk under its checked
absolute file place and checkout/root scope. Git locations bind the same place
within the same checked scope, rather than merging equal bytes. Root retargets
create new identities. Explicit `GitFileMove` evidence still verifies existing
disk moves. Complete located publication also prepares automatic cross-path
correspondences from captured and retained local Git snapshots. A correspondence
needs an explicit `git diff -M` rename, local commit ancestry, both complete
regular blobs and the same checked checkout/root scope. Equal text in unrelated
histories or copied files supplies no correspondence. Disk inputs anchor only at
a checked natural place with identical complete Git bytes. A uniquely
corroborated committed disk move additionally satisfies the existing
absent-source/old-version move checks; reused old physical paths and conflicting
identities are refused atomically. Tracked stash trees participate; a stash's
untracked third-parent tree cannot supply tracked rename evidence. All
correspondence evidence is read again before publication, and the selected proof
is retained with its location. Uncommitted cross-inode moves without that
evidence still create a new identity.

After every location is validated, absent file/chunk location rows retire in
the same transaction. The private located dependency producer applies
the identity-selected baseline policy and guarded unlocated collection in that
transaction. Without that producer, publication retains the unlocated rows.
Restoration selects the exact version's own location pins; a newly allocated
location never borrows the later disk version's baseline automatically. Public
ingest composes this producer. Mechanical detection runs automatically after
complete located publication; see [reconciliation.md](reconciliation.md).

Changed captures can provide `file_handoff(connection, AppliedLocatedFile)` and
`batch_handoff(connection, LocatedCaptureResult)`. Both run after the complete
prospective identity/location catalog exists, inside its transaction; errors
roll back publication and activity. They must not nest/commit transactions or
invoke providers. Generic no-op captures invoke neither callback and rewrite no
identity, inventory or audit row. The complete dependency producer explicitly
opts into unchanged captures for settings-only eligibility and source retries;
its typed decision contributes actual dependency mutations to the publication.
True no-ops remain quiet. The result carries the publishing repository even
when its capture is empty, plus the caller's activity and cumulative-count hook
for affected foreign scopes.

After all handoffs, publication rereads the complete capture, Git correspondence,
root scopes and physical disk identities before commit. A complete producer's
optional `verify_in_transaction` runs after reply callbacks and validates its
foreign acquisitions against that exact connection/result. A source-byte change or
new Git ref after the last individual pin guard rolls back every file, policy,
collection and activity write. `AppliedLocatedFile.previous_versions` records
the prior exact versions from that same location for the identity policy.

Complete disk and located publication revalidate the effective settings before
writing and after producer/reply callbacks, using the original settings path
and home normalization. Changed enablement, roots or other effective settings,
unreadable settings and late physical/Git capture changes roll back the full
publication and its activity. Comment/format-only settings changes preserve
the same authorization. A recreated unindexed raw source path cannot hide
behind a retained recognized-move anchor.

The first publication guard validates a caller-supplied manifest against an
independent scan using committed history. Later guards reuse only that validated
capture while rereading source bytes, physical roots, complete raw candidate
inventory, ignore policy and Git refs. Preliminary captures never advance stored
hashes: a later same-size/same-mtime edit is still observed. Configured-store
proofs cover no-resplit repeats, corrupt-cache fallback, forged input refusal,
changed source/settings and callback rollback. Separate dual-root store fixtures
verify document origin, heading chunks and portable reads on disk and in local
branches with narrowed code subdirectories and shared skip/ignore rules.

## Multiple clones of one repository

Configured `code_clones` share the repository's chunk identities and exact versions. The calling checkout selects the disk location; the primary checkout keeps the legacy `disk` key, while another clone has a canonical location record containing its resolved path. Local branch and stash records carry that clone too. Capturing one checkout leaves the other checkouts' inventories, locations, pins and policy intact. Requirement and decision rows retain their UUID identities in all three location kinds.

A complete pass reserves its own location before capturing. Different clones can capture simultaneously; publication takes the short repository pass guard, and every location reservation also protects against repository removal. A supplied manifest must belong to the selected clone. Collection removes a version only after no location or retained owner needs it. Overview projections and current resolver reads select the calling clone; equal exact versions can retain different location-owned policy, stale reasons and verifications.

The developer check `scripts/check_real.py --second-clone garden=/path/to/another/garden` copies both checkouts and their artifact corpus into a private temporary directory, uses only a disposable check database, measures both locations and checks shared exact versions. Its disposable settings disable embedding credentials, so the public search check exercises wording fallback without using the owner's provider key. Reports belong outside repositories and corpora.
