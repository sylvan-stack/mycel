# Summary plans, reports and writer boundary

`mycel summaries [status] [--repo <name>]` reports one enabled repository.
`mycel summaries build|regenerate --dry-run [--repo <name>]` returns a plan.
Scope comes from one literal repository or a current directory inside its
configured corpus roots. Organizations and repeated repository selectors are
invalid. All three operations use a checked read-only repeatable snapshot,
perform no freshness pass, start no writer or embedding call, and write no
store rows or activity. An ended snapshot cannot be reused. Empty repositories
return successful complete reports. An absent set omits the optional built time,
profile and Build fields, and reports an empty numerical-version object. A set
published from development source also omits Build. Reports and dry-runs
need no writer.

Eligibility is current on-disk document sections fully embedded with the
selected model/dimensions and exact validated part plan. Heartwood documents,
documents declared `generated`, code, overview and summaries are excluded.
`notEmbedded` counts only otherwise eligible document sections lacking complete
current coverage. Status divides those sections into disjoint `inSummary`,
`inNone` and `notEmbedded` counts; overlapping memberships count each section
once. It reports summaries in level/number order, stale counts, configured
writer presence and the set's recorded grouping, Build and numerical metadata.

The initial grouping profile is `mycel-summary-v1`. Canonical root/path/position
order precedes arithmetic means of every member's embedding parts. PCA uses
`min(10, dimensions, n-1)` components when reduction is needed. Spherical
Gaussian mixtures use random seed 0, covariance regularisation `1e-4`, and
candidate counts `1..min(150, n-1, ceil(n/8))`. Lowest BIC wins, then fewer
components. A member enters every component with probability at least `0.10`;
if none qualifies, the highest probability wins, then the earlier component.
Fitting runs with one native thread and a scoped `OMP_NUM_THREADS=1`, restored
on exit, so macOS physical-core detection starts no subprocess. Empty groups
are discarded. Zero members produce no groups; one or two produce
one group. Non-finite inputs or fitting failure return an explicit grouping
failure. The numerical versions are pinned with the offline Build and reported.

Build dry-runs include ordered groups, promoted singletons, bounded request
counts and at most five levels. A statistical singleton is promoted without a
summary. Planning stops when the top contains ten or fewer summaries/promoted
members together, or a level produces no summary. Level-one requests use exact
complete text and the writer's splitting/cut rules below. Higher levels use
mean member vectors and estimated requests; generated text and its embedding
are unavailable during a dry-run. The reply explicitly labels this estimate.

Regeneration dry-runs keep stored logical membership and readable places,
select surviving current member versions and process stale summaries from
lower levels upward. Missing members are removed from the planned request;
summaries with no surviving member are planned for removal. Still-stale
generated members block their parent. A parent whose lower member is planned
to succeed is conditional on that success. Plans expose complete write,
remove and blocked work plus exact historical/current/missing members and
conditional lower-level writes/removals. They label their assumed lower-level
success policy; regeneration never regroups. `write` lists stale candidates
conditional on lower success and a single bounded request. Work details report
`boundedRequestsForCurrentText`, `requestFits` and `requiresBuild`; a fixed group
that already needs splitting is marked as requiring a build unless a planned
lower write can still change its request bytes.

`mycel summaries build [--repo <name>]` builds a complete new tree. Missing or
invalid generation configuration returns `settings`; an unavailable executable
is refused before the store is opened. Each level uses complete actual writer
responses, embeds them with the ordinary current-model planner, and only then
groups the next level. Statistical singletons move up without a request.
Requests split by the same bounded framing used by the dry-run. The reply names
cut sections, redacted request/embedding failures, and `notEmbedded` sections.
`written` counts committed summaries; a failed build reports zero.

One nonblocking summary-operation lock and an exact live invocation protect
the entire build. Pass locks are released throughout writer and embedding
calls. All staged summary text, plans and vectors remain outside the searchable
tables. The final transaction rechecks current source membership, exact bytes,
vectors, effective settings, prompts and executable identity before replacing
the old complete tree with text, vectors, generated pins and evidence together.
Final checks follow the mutation audit. Changed inputs report
`stopped: "inputs_changed"`; failure or interruption preserves the old set.
An empty eligible set succeeds and retains its built time, grouping profile,
Build and numerical versions. Cleanup releases the invocation's private leases.

`mycel summaries regenerate [--repo <name>]` repairs stale summaries in ascending
level and canonical place order. It retains each summary's logical identity,
readable place and surviving stored membership; added document sections enter
only through a later build. An ingested recreation of an original document
member reconnects at its retained natural place when its old identity is gone;
unrelated new sections stay outside the set. Each successful response is embedded and published
with its exact generated pins in one guarded transaction. Its text, vectors and
pins become visible together. The set's original build metadata is retained.
Independent successes remain if a later request, embedding or input guard fails.
Still-stale generated members block their parents with `stale_member`.
Missing-member summaries are deleted before their parents are considered.
Changed inputs preserve the old stale summary and report `inputs_changed`.
If changed fixed membership now needs more than one bounded request, it is
blocked without calls; a new build is needed to split that membership.

Regeneration holds the summary-operation lock and exact invocation liveness
while releasing pass locks during writer and embedding calls. Private request
and response evidence stays protected until publication or discard. Interruption
cleans up requests and leases while retaining acknowledged publications. The
complete reply reports committed `written` and `deleted`, `replaced: false`,
redacted `failed`, canonical `blocked` and `cut`, and any `stopped` reason.

`mycel summaries remove [--repo <name>]` deletes the current summary set, its
metadata, vectors and generated edges together under the summary/pass guards.
It releases only evidence with no remaining owner, preserving independently
referenced evidence. No generation setting, writer call or embedding call is
needed. Empty removal succeeds with `removed: 0`; the reply counts summaries
actually removed. Numbered Builds record the mutation and exact final counts
in the same transaction. Concurrent summary mutations return `busy`.
If final auditing or connection cleanup fails after an acknowledged publication
or removal, its committed counts remain in the reply with
`countsState: "committed_prefix"` and the error. Caller interruption returns
exit 2; other failures return exit 1.

The publication handoff includes pure complete-reply constructors for
`SummariesResult` and `SummariesRemoval`. They validate nonnegative counts,
repository-owned canonical places, ordered failures/blockers, closed redacted
reason codes and empty success. Constructing a reply performs no publication
or removal; mutation handlers supply their actual committed counts.

The planner renders every section with the MYC-3 document place line and its
complete exact text. Canonical root, path and source position determine order.
The built-in instruction and task preserve version 1's wording. An optional
`summaries.instructions` folder replaces them with `raptor-summary.md` and
`raptor-request.md.tmpl`; both must be nonempty UTF-8, and the task must contain
exactly one literal `$sections` marker. Prompt failures are redacted `settings`
errors before generation. No project, Arbol or legacy instruction file is
read to obtain the packaged defaults.

Each complete request, including instruction, task, place lines and separators,
fits 48,000 Unicode code points. Large groups split recursively into ordered
halves, preserving every member. A single oversized section keeps a prefix
followed by `[Mycel: source text cut at request limit]`, with the notice inside
the same budget. Its qualified place appears in the request's `cut` report.
Framing that leaves no room for source text and the notice is refused before
a call. UTF-8 byte counts and character counts are distinct.

The writer starts literal `summaries.command` argv without a shell in a fresh,
empty temporary folder for each attempt. The entire request goes only through
stdin. At most `summaries.at_once` attempts run concurrently. Each attempt has
five minutes, a 1 MiB stdout cap and a 64 KiB stderr cap. Nonzero exit, invalid
UTF-8, empty/whitespace-only output, overflow, start/I/O failure or deadline
failure receives exactly one retry. Successful response bytes remain whole.
Failed results contain only fixed reason codes and attempt counts. Raw stderr
and command values never enter failure replies. Timeout, overflow and
interruption terminate and reap process groups.

Generation evidence stays private to the operation. An immutable manifest and
owner-scoped snapshots retain exact request bytes/hash, prompt bytes/hashes,
literal argv, ordered places and exact member identifiers/versions. Cuts keep
both the full source and the exact text sent. An active connection-bound
invocation owns the request lease before writing starts; a successful response
adds immutable exact response evidence. Reading verifies every blob and
manifest. The build consumer rechecks source inputs under its locks, transfers
successful evidence ownership with generated rows atomically, and releases
unpublished staging at operation completion. Distinct attempts at identical
requests retain separate invocation-owned leases for their exact responses.

The version-1 publisher handoff uses `mycel_generated_state` summary rows with
exact chunk version/level, ordered logical member UUID/version/hash/place pins,
and shared set metadata (`builtAt`, profile, Build and numerical versions).
Every active summary must have compatible state matching its current index
version and set metadata. The reader refuses incompatible rows. Build publication persists metadata for
an empty accepted set independently of summary nodes in a versioned index-only
set record. An absent set omits optional metadata; an explicitly published empty
set reports its historical metadata.

The successful generated provenance hook is implemented separately in
[generated.md](generated.md). It publishes whole exact response text, its index
location, compatible version-1 summary state and every generated pin/evidence
owner in the caller transaction, then mechanically recomposes higher levels.
It supplies no vectors, grouping loop, external call, complete-tree replacement
or public mutation handler. For real generated rows the report validates
request membership and evidence and uses the same document-body comparison
as mechanical detection; exact byte/version checks still gate publication.
Existing prepared version-1 state without generated dependencies retains the
strict state-only planning fallback. The complete-tree publisher replaces the
old set within its transaction before publishing nodes with new set metadata,
and supplies empty-set metadata and private staging.
