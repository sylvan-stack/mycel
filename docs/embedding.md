# Scoped embedding and offline plans

The local planner prepares complete chunk and query inputs without contacting a
provider or changing a database. `mycel embed` now connects that planner to
retained exact text, guarded persistence and the Voyage client. Public `search`
uses bounded query embedding. Live compatibility is a separate, explicitly
selected check described below.

Use `mycel embed --repo core` for one configured repository, repeated `--repo`
flags for several, an organization name for its enabled configured members, or
`--all` for every enabled configured repository. With no selector, the containing
configured repository or organization folder determines scope. An unrelated
current directory is refused. Literal selectors are deduplicated. Unknown and
disabled selections retain their local errors alongside other repositories;
an invocation with no eligible selection is refused before store access.
Embedding uses retained disk, branch, stash and current index-only text and
needs no folder scan. Overview sections use document input rules and their
canonical index place line; unchanged outlines retain their existing plans and
vectors. A changed outline joins ordinary pending work, and explicit
`ingest --embed` embeds it after atomic pass publication.

`--dry-run` reports the exact chunk/version identities, ordered input ranges,
saved place lines, submitted/planning token counts and local planning failures.
Its provisional plans count before any row has been saved. It changes no feature,
receipt, activity or lock-key rows, never drains paid receipts, and acquires no
embedding credential. `--retry-failed` additionally selects failed parts or
remakes failed plans, retaining successful parts. A retry dry run reports that
selection separately from ordinary coverage: `pending` still describes what a
subsequent pass without the retry flag would send.

Each repository reply distinguishes total embedded, pending and failed chunk
versions from part counts. These three version counts are disjoint. `sent`
counts versions made complete in this invocation; `parts.sent` counts vectors
actually published, including recovered paid receipts. Partial versions never
count as embedded. Deferred paid results and quarantined obsolete receipts
have separate counts. Ordinary next-pass parts exclude failures and deferred
results. A configuration change that disables/removes a repository or changes
the selected model/dimensions zeros its pending counts in the stopped reply.

The captured send inventory is finite. Versions added while requests run remain
pending for a later pass. Requests and isolated/retried sub-batches recheck the
current settings before acquiring the embedding key and before every send.
Plan/vector publication rechecks settings and store generation within the
transaction and after activity attachment. Paid responses still enter durable
receipts if settings change during a request; their publication is refused.
Completed batches survive interruption and later provider failures. When every
initial capture/plan read fails before repository work starts, the reply is the
common per-repository envelope, preserving every refusal. Caller interruption before work starts uses the common
stopped reply with exit 2. A
completed dry-run report keeps its per-repository results even when planning
fails locally. Once work starts, interruption preserves the full progress reply.
If the final store read is unavailable or interrupted, `countsState="committed_prefix"`
labels counts projected only from the captured inventory and acknowledged
transactions; these cannot claim a fresh complete inventory.

Numbered Builds attach `embed` activity to plan saves, paid receipt staging and
guarded publication in those same transactions. Finished entries copy the exact
repository reply and stopped/failed outcome. Empty passes leave no activity
entry. Source development has no invented Build number. Store acceptance uses
individually created/discarded configured PostgreSQL databases and injected
offline service fixtures; no acceptance check sends paid provider requests.

The initial model is `voyage-code-4`, with 256, 512, 1024 or 2048 dimensions
(1024 by default). Its official tokenizer is packaged in the program at revision
`ac780b405e54ff8b3aff681270e0e03840fed2f3`, with SHA-256
`c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539`.
Loading verifies that file and the pinned `tokenizers==0.23.2` library, disables
padding and truncation, and records the installed library's digest. It never
downloads an asset at runtime. The tokenizer license and source metadata are
packaged beside it.

The accepted catalog uses conservative limits of **31,744 tokens per complete
input and batch**, **64 inputs per batch**, and one in-flight request per
repository. The provider context limit is 32,000 and the published input-count
limit is 1,000. The conservative batch cap avoids assuming a code-4 aggregate
allowance that the provider has not documented. These values come from the
accepted MYC-3 catalog; the [Voyage documentation](https://docs.voyageai.com/docs/embeddings)
and [official pinned asset](https://huggingface.co/voyageai/voyage-code-4/tree/ac780b405e54ff8b3aff681270e0e03840fed2f3)
provide the provider evidence.

Every part starts with a saved place line and a newline. Code uses
`<path> — <symbol> (<kind>)`; documents use `<path> › <heading path>`.
A preamble or empty heading has an empty heading path. The stored body stays
exactly as read, including headings, whitespace, Unicode composition and its
final characters. Queries are submitted exactly as typed, with query input type
and no added place line.

Counts distinguish the exact submitted string from the provider prompt plus
that string. Both must fit. The provider's document/query prompt is counted for
planning and is not inserted into the submitted text. Submitted counts remain
available for comparison with provider usage. The live report retains agreement
and signed provider-minus-submitted difference as diagnostics; provider usage
never replaces the pinned counts used for planning limits (MYC-D42).

Planner version 1 first tries all remaining text. Otherwise it uses the last
original character covered by the first input-cap tokens as a tentative end,
tries the latest paragraph boundary (documents) or line boundary (code) that
fits, then retreats by original Unicode characters if needed. Every chosen
complete input is measured again. Parts have consecutive half-open UTF-8 byte
ranges whose concatenation is the entire original body. An empty body has one
place-only part. An impossible place line or input produces an explicit local
failure without discarding text.

Plans retain repository, logical chunk and exact-text version identity, complete
text hash, model/dimensions, saved context, ordered parts, both token counts,
tokenizer file/library pins, catalog digest, planner revision, prompts and limits.
Retained plans must verify their recorded tokenizer/library and counting context,
exact ranges, counts and full text before batching. Changed caps are checked
against the saved inputs. A plan that cannot be verified must be replaced through
persistence operations; the planner never silently treats it as covered.

Persistence retains complete chunk text, saved part inputs and durable JSON
receipt payloads as exact bytes. PostgreSQL's NUL-free BM25 projection does not
enter planning, provider submission, receipt integrity or restart recovery.

Batches sort by repository, chunk identifier, exact version and part order,
ending before either cap or the repository/model/dimensions changes. They carry
document input type, float output and `truncation=false`.

Persistence saves plans before sending their parts. Its finite inventory leaves
concurrently added versions pending until a later session.
Validated provider results first enter a durable receipt, then publish under the
repository pass guard. A busy publication stops further sends; the next session
drains the saved results without paying for them again. Only versions actually
removed from the store may discard their results. A historical batch can publish
after current batch limits change when its individual saved inputs remain valid.
Genuinely incompatible inputs retain their original paid payload in a validated
quarantine envelope, expose separate obsolete counts and allow replacement plans
to proceed. Corrupt receipts produce an explicit refusal.

The provider API validates every returned vector before staging a batch,
uses bounded retries for transient failures and isolates content-specific failures.
Its deterministic integration checks use service fixtures without provider calls.
The persistence and provider APIs satisfy the original SYL-116 and SYL-117 scopes.
Configured-store acceptance covers atomic guarded publication, deletion races,
rollback, durable receipt recovery and public scoped command progress. Public
`ingest --embed` uses the same scoped embedding command after publication.
Automatic acceptance makes no live compatibility claim for a Build; that claim
requires its own explicit provider operation.

## Explicit live compatibility check

The internal on-demand `run_embedding_live_check` helper requires explicit live
selection and uses one fixed short document text and one fixed query through
the normal configured Voyage client. Each request has one attempt. It checks
configured model/dimensions and retains reported input-text token usage, the
packaged tokenizer's exact submitted-string count and the larger conservative
planning count separately. Version 2 (`mycel-embedding-live-v2`) adds
`tokenCountComparison` with `matches` and signed `providerMinusSubmitted`.
Disagreement is diagnostic and does not fail compatibility under MYC-D42;
invalid provider responses, credentials, model, dimensions and local planning
failures still stop the check. The pinned tokenizer continues to enforce every
input/batch cap. The report names Build, model, date, tokenizer provenance and
observed timings. Unknown cost remains null.

This helper opens no store and writes no vectors/settings. Automatic tests use
internal service stand-ins, which are always labelled and cannot pass real
live acceptance. Historical version 1 reports retain their strict-equality
contract; a passing version 2 check requires its own genuine operation. The
helper adds no public endpoint override or automatic call.

<!-- sources:
mycel:@code/src/mycel/_embedding_live.py#run_embedding_live_check
mycel:@code/tests/test_provider_evaluation.py
-->
