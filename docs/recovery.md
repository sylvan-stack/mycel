# Origin recovery

`mycel recovery` proposes Origin Links for current chunks that have none.
Use a Build that includes this command; earlier Builds omit it. Recovery reads
an already ingested snapshot, checks it against the calling clone and judges
local candidates. It never performs an ingest, embedding, fetch or remote read.

```sh
mycel recovery 'cellar:@code/src/retry.py#RetryPolicy.allow' --dry-run
mycel recovery --repo cellar --path src --dry-run
mycel recovery --repo cellar --k 20
mycel recovery --repo cellar --path src --review
mycel origins --repo cellar --no-fresh
```

A chunk reference selects its repository. Otherwise select one enabled
repository explicitly or through the current folder. Paths repeat and match
component boundaries. `--k` caps exact preparation attempts, including unresolved
pairs; one chunk can have several candidates. Repository and path scopes select
unlinked code and non-authored document chunks. Requirement/decision rows and
authored documents remain candidate Origins; an explicit chunk reference may
select them. Tests are neither selected nor candidates: a test's Origin is the
requirement it checks, stated with `mycel justify`, and naming a test chunk is
refused with `invalid_input`.
`--review` instead selects existing inferred/recovered links in that scope.

## Candidate sources

| Source | Local evidence |
|---|---|
| `document` | Document sections joined by a direct Source Ref in either direction, or whose text names the complete symbol; a symbol that more than ten document sections name is not distinctive and gives no name matches |
| `commit` | The introducing commit found by local Git symbol pickaxe, plus an indexed snapshot naming its full hash |
| `issue` | An indexed time-pinned snapshot naming an upstream issue/PR URL in that commit; a bare #number matches only issue/PR URLs in the same repository's corpus |
| `embedding` | The four requirement/decision chunks nearest to existing complete current-model vectors of the selected chunk, by rank |

An entity candidate uses its Entity URI; another uses its qualified address.
Duplicates merge their source categories and receive one judgement. No vector
is bought for recovery. Missing chunk vectors disable only that source. Missing
commit/issue snapshots stay unavailable; the command does not fabricate an
Origin address or copy a remote page. Snapshot external truth first, then ingest
it, following the [Source Refs guide](source-refs.md). A raw local commit is
retained as exact context even when no snapshot can serve as an Origin.

An owner's requirements and snapshots of upstream documents/issues can govern
third-party code. Linear snapshots, tasks and Beats are excluded before
judgement. Candidate text mentioning a symbol or a commit is a proposal to
judge, not a proof of authority.

## Judgement, scores and review

The packaged `mycel-origin-v1` question asks whether a candidate `governs`, is
`related` to, or is `unrelated` to the selected chunk. It is distinct from the
question about continued support in [drift classification](classification.md).
The request contains complete exact chunk/candidate texts, direct-governor and
ancestor context (without the code a governor cites), local history, source
categories and actual model/reviewer identities. Its canonical input hash binds all those semantic inputs. Inputs
are data, never instructions; required text is never truncated.

Only a complete `governs` result writes a link, with the model's score. Its
method is `recovered` for commit/issue provenance and `inferred` otherwise. A
`related` or `unrelated` result writes none. Without a configured reviewer,
Jev's probability of `governs` decides: it must reach `drifts.origin_floor`
(0.7) and is the link's score; a lower probability ends the pair without effect. Scores at least 0.5 have band `inferred`;
lower ones have band `candidate`. Recovery and review keep these bands even
when a model returns a high score. They do not produce a statement, a check
proof, a verification or a freshness confirmation.

Model claims have dependency kind `origin`, separate from the source-policy
graph. A document can therefore cite code and also be proposed as its Origin
without circular authority. The statement command `justify` can supersede the
matching model proposal, applying its ordinary guarded assertion/verification
rules. `origins` lists both kinds of link through the same report.

`--review` calls only the configured independent smarter reviewer. Its strict
protocol-1 reply includes `confidenceScore` in [0,1]. A `governs` review
raises or lowers the score, recomputes its capped band and records
`review: {who, when, outcome}`. A `related` or `unrelated` review withdraws only
the model's proposal; it never withdraws a statement. With a reviewer
configured, ordinary recovery also routes low canonical confidence, ties and
oversized Jev input to it. Without one, oversized input remains
`needs_llm_review` with its reason.

## Guards, budgets and reply

`--dry-run` writes nothing, takes no Jev/reviewer/Voyage credential and launches
no model adapter. It may read the store password when the store asks for one,
and runs only permitted local Git reads. It lists source availability,
candidates and provenance, quiet-period eligibility and exact payload/Jev byte
counts for prepared pairs. Canonical chunk/origin order bounds preparation before
expensive evidence assembly. `capped: true` reports uninspected work; discovered
candidates beyond the cap have `status: not_selected` and no preparation. Prepared
pairs are ordered by eligibility within that prefix. The reply's maximum-call figures are upper bounds, not a request to
execute those calls.

Non-dry execution uses `[drifts]` candidate, quiet-period, confidence-floor,
byte, attempt and deadline settings. It runs one pair at a time, within
`at_once`. Only typed transient errors retry, within the finite original
invocation; cancellation ends the active transport/process and retains the
completed prefix. There is no worker waiting for debounce expiry.

The check immediately before each call and before each application covers complete files, current clone/version,
local history, enablement, required context and the actual reviewer executable
fingerprint. New bytes with a restored mtime retain their first observed quiet
period. Obsolete, corrupt or missing inputs produce no link. Final input guards
also cover changes during the writing/audit transaction. In-flight requests
own their exact text snapshots and canonical payload in the Index Store;
current links keep their evidence. Other ended requests retain at most the
newest 1,000 per repository. Reuse validates the original stages and identities,
not just a matching hash. The new question requires its own live qualification
before deployment; passing automatic stand-ins supplies no provider proof.

## A series of steps

A repository or path run is one step of a series. Each step keeps every
judgement that changed nothing under its exact chunk version, candidate version
and judgement policy (question, model, floor, byte limit and reviewer
identity), beyond the 1,000-request retention. The next step skips those pairs,
and skips a section all of whose candidates were judged, until its text, a
candidate or the policy changes; a changed floor alone reuses them. Repeat the
command until the reply says `complete: true`:

```sh
mycel recovery --repo cellar --k 50
```

`RecoveryReply` is one object with `repository`, `dryRun`, `review`,
`selected`, `completed`, `jevCalls`, `reviewCalls`, `errors`, `incomplete`,
`capped`, `status`, `maxCalls`, `chunks` and `pairs`; a step of a series adds
`remaining`, `complete` and `skipped`. Each chunk includes its history,
embedding and per-source availability and candidates. Selected pairs add their
input hash, exact byte counts, eligibility, attempts, stage results, final
judgement/score and applied `link` (null for `related`, `unrelated` or a
probability below the floor). A candidate an earlier step judged shows
`status: judged`. Pending debounce or
missing reviewer configuration is ordinary pending work. An operational fault
sets status 1; interruption sets 2. Completed applications remain in the reply.
Numbered Builds record committed link writes/withdrawals in activity history.

<!-- sources:
mycel:@code/src/mycel/_recovery.py#run_recovery
mycel:@code/src/mycel/_recovery.py#RecoveryStore
mycel:@code/src/mycel/_classification_payload.py#OriginDecisionPayload
mycel:@code/tests/test_recovery.py#RecoveryStoreTests
-->
