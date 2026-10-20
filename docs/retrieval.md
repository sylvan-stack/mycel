# Scoped retrieval and deterministic ranking

Public `search` composes the SYL-126 candidate producer, SYL-127 ranking,
SYL-128 freshness and SYL-129 evidence-bearing schema3 replies. It resolves literal
configured repository names, organization names/folders and the repository of
the current directory. No repository name supplies a fallback. Disabled
repositories contribute neither local results nor shared documents. A query
must contain non-whitespace text; the result count is an integer from 1 to 100.

Each enabled member of an organization receives its own scoped candidate
lists and requested count. Scores are never compared across member replies.
Both arms retain at most `max(k, 20)` distinct logical chunks per repository.

## Result scope

The producer reads current disk versions in one PostgreSQL-enforced
read-only, repeatable-read snapshot under the shared store-format guard.
Branch-only, stash-only and away versions are excluded. Corpus origin decides
whether a chunk is code or a document; Markdown under a checkout remains a
document with its actual code-root address.

Document-inclusive and document-only selections add only the enabled
`search.shared_documents` entries. A file selects that exact artifact-root
path; a folder selects its descendants recursively. Physical aliases retain
one chunk identity, including a shared artifact alias whose canonical address
uses the code root. Code-only selection adds no shared documents.

## Matching

BM25 scores the complete stored text, name and path. It uses a deterministic
Unicode wording tokenizer and scoped document statistics. Missing, partial,
failed or historical-model embeddings never remove wording access.
The score uses positive smoothed Robertson IDF, `k1=1.2`, `b=0.75`, exact
scoped token lengths and one contribution per distinct query term. The
coefficients follow the [Tantivy BM25 baseline](https://github.com/quickwit-oss/tantivy/blob/main/src/query/bm25.rs);
the new complete text/name/path input and scoped statistics are explicit.

Meaning matching uses cosine similarity over every part of a complete plan
for the configured model and dimensions. Retained plan metadata, exact input
bytes, ordered part coverage and vectors are checked before a version is
eligible. A chunk's score is its best matching part; repeated part hits consume
one candidate slot and add no score. Both lists use a stable place/identity
order to break ties.

The snapshot performs no DDL, embedding calls, freshness pass, activity,
settings copy or feature writes. A caller prepares its query vector before
entering the snapshot. An absent vector leaves the wording candidates usable.

The current implementation reads the enabled disk catalog and complete vector
parts, then computes exact scoped candidates in memory. Initialization still
creates and validates the ParadeDB BM25 and pgvector indexes. This producer
does not claim identical index tokenization, approximate-neighbor behavior or
large-corpus performance; its CPU and memory cost grows with the catalog and
parts. Later query planning must preserve complete current names/paths and
logical-chunk collapse before every limit.

## Integration boundary

This producer supplies candidate lists, complete selected chunk metadata and
coverage state. `CandidateSnapshot.ranked` composes the SYL-127 ranking core
with the exact disk-owned citation reader described below. SYL-128 supplies
the recursive freshness consumer described below; SYL-129 composes public search
replies, citations and degraded-mode reasons. Nonempty public retrieval
evaluation uses the normal search adapter and produces an explicit on-demand
MYC-4.25 measurement. The ranking uses the accepted initial constants; it changes
no provider qualification or evaluation requirement.

## Ranking routes and weights

The stripped query takes the identifier route when its entire shape matches
Unicode word characters plus `.`, `#`, `/` and `-`. One plain word follows
that route. Each arm contributes `1 / (60 + rank)` with equal weight and
one-based distinct logical-chunk ranks. Other queries take the question route:
meaning hits retain their cosine score, while wording-only hits form a separate
tier below every scored hit, including negative cosines. The tail orders by
weighted BM25, without comparing its numbers with cosine scores.

Every entry receives its family factors after route scoring and any agreement
boost, whether it entered directly, through a bridge or through wording alone.
Repository `test_patterns` and `generated_patterns` regular expressions use
the packaged defaults unless overridden, including an explicit empty override.
Patterns see the relative path with normalized separators and also a leading
slash for folder-boundary matches at the root.

Tests receive `0.85` on the identifier route and `0.93` on the question route.
Generated code receives `0.93` on the question route and no identifier factor.
File, module, markup and style chunks receive `0.75` and `0.9` respectively.
Overlapping factors multiply once each. Bounded, case-insensitive query words
`test`, `spec`, `e2e`, `mock`, `fixture` (including their ordinary plurals) lift
the test factor; `type`, `schema` (and plurals), `graphql`, `gql`, `codegen` and
`generated` lift the generated factor. Structural factors always apply.

## Document bridges and citations

For a question with a query vector, the eight closest own document sections
are selected from the full current-model cosine pool, independently of the
direct candidate limits. Each section contributes at most the three closest
fully embedded cited code chunks in the searched repository. The inherited
score is the section cosine times `0.92`. A code chunk found by both direct
meaning and a bridge receives `0.05` exactly once on top of the stronger raw
score. Wording membership alone supplies no agreement boost. A bridge records
its strongest supplying section in `via`, even when the direct score wins.
Repeated refs, sections and embedding parts never multiply that contribution.

The citation reader follows only declared or asserted Source Refs owned by
the exact current disk file location and dependant version. It resolves the
natural current source selection through the existing retained-anchor resolver,
including recognized moves, file selections and class families. Branch/stash
declarations sharing a version, relations, generated edges, invalid/ambiguous
refs, disabled repositories and old pinned source versions supply no targets.
The reader follows one hop and cannot widen returned code scope.

`documented_in` selects at most two distinct fully embedded visible citing
sections by descending best-part cosine, then the canonical tie order below.
Selected shared documents can cite code in mixed searches but cannot deliver
bridge code. Code-only ranking consults own document cues and omits shared
documents and document results; document-only ranking disables bridges.

## Document admission and deterministic order

In a mixed search, a document must have a complete current-model cosine at
least `0.03` above the best raw direct code cosine from the full selected pool.
Bridge boosts, RRF and family weights do not move that bar. At most two
documents are admitted and routing basenames `INDEX.md` and `README.md` are
excluded. These rules apply to both arms and routes. Machine roundoff at an
equal margin is accepted within four ULPs. Negative code cosines use their
actual maximum; an empty eligible code pool removes the comparison. Without
a query vector, mixed document results are omitted. Document-only searches
have no margin, routing-file exclusion or two-document cap.

Results order by score tier, descending weighted score, then
`(path, root, name, repository, logical identifier, exact version)`. Bridge
choices and citing sections use descending raw cosine then that same tuple.
Each enabled organization member receives its own ranking and result limit.
The graph, text, places, vectors and settings remain in one read-only,
repeatable-read snapshot, and an escaped snapshot lease refuses further use.

## Recursive freshness

The internal `run_store_freshness` consumer fixes the enabled result members
and `only` selection before checking sources. It uses every selected current
disk chunk, plus the enabled configured shared-document suppliers for searches
that include documents. Declared and asserted Source Refs extend its upstream
frontier recursively through their exact current source members. Valid missing
refs and retained missing-source places still require their enabled repository
to be checked. Invalid and unresolved refs remain explicit faults. Relations,
ordinary text mentions and semantic similarities create no upstream authority.

Sources are ingested before their dependants when the known graph permits it.
Newly captured declarations can defer a publication while newly required
sources are checked; the owner retries only after actual source progress.
Complete ingest captures both corpora and local branches/stashes, then applies
the existing guarded identity, dependency, collection and mechanical staleness
producers. Checking an upstream never changes the result selection. A code-only
search can check governing documents through explicit dependencies while
returning only code. Downstream owners that need dependency-state updates are
reported separately and receive no additional file scans.
An affected dependant whose physical bytes differ from its indexed version
keeps its existing evidence and is reported pending until its own required
ingest can reconcile those bytes. That deferral does not abort a needed
upstream publication or scan an unrelated dependant's files as a new scope.
Prospective discovery follows new files, new sections and retained heading
identities within exact current file bindings. A relocated source still needs
the ordinary ingest's checked physical or Git binding; a new unresolved
upstream ref can leave that pass refused or failed. Its dependant's exact
dependency check stays incomplete and the current index remains usable.

One absolute monotonic deadline includes discovery, recursive capture, guarded
publication and propagation. Nested disk readers, Git subprocesses and SQL
statements share its remaining allowance; a final transaction check prevents
publication after expiry. Owned lock cleanup and closing existing activity
entries can finish after the work allowance without starting another check.
An incomplete check leaves the committed index available to the later search.
Each required repository reports `done`, `pending`, `busy`, `refused` or
`failed`, with an incomplete-work reason. Partial discovery, unstarted work and
pending downstream updates prevent overall completion. Ref faults separately
prevent an affected exact chunk's dependency check from being complete, even
when all eligible repository work finished. Unvisited citation keys remain
incomplete. Completing a mechanical check supplies no semantic verification.

`no_fresh=True` performs only a read of known explicit dependency ownership:
all known required repositories are pending and every exact result check is
incomplete. It captures no files, creates no activity and starts no publication.
Freshness never regenerates dependant text, renews unchanged dependant pins,
plans or runs embedding, or calls a classifier or reviewer. File edits still
follow the accepted complete-ingest identity and initial-pin rules.

These are internal facts for SYL-129's public reply assembly and SYL-130's
reading consumer. The public `search` handler composes this boundary. The caller
must run freshness before opening its independent read-only candidate/ranking
snapshot, and prepare any query embedding outside that snapshot.

## Public search replies

`mycel search <query> [--repo <name>] [--k 1..100] [--only code|docs]
[--no-fresh]` returns schema 3. Repeated repository selectors retain separate
rankings. A named organization, including one with only one enabled member,
returns `{schema: 3, organization, repositories: [SearchReply, ...]}`.
Other multiple selections return `{schema: 3, repositories: [SearchReply, ...]}`;
a single repository returns its SearchReply directly. Scope and store-format
preflight finish before any query embedding request. Use `--` before a query
that starts with an option prefix.

Every member reply contains `repository`, `route`, `meaning: {used, reason?}`,
distinct `candidates: {meaning, wording}`, `freshness`, and `results`. A query
is sent once per invocation through the bounded Voyage query adapter using
complete text, the configured model/dimensions, query input type and no
truncation. Missing credentials, local query limits, provider failures and
unusable vectors preserve wording results with a sanitized reason. A store
dimension mismatch skips query embedding entirely and explains that `mycel
init` must align the structure before meaning matching can resume. Caller
cancellation reaches the normal stopped command reply. This query request
creates no saved document embedding plan or vector; pending corpus embedding
is never started by search.

Freshness starts after query preparation and shares one configured allowance
across all required ingest and dependency propagation. The final candidate,
ranking, citation and mark reads share one read-only repeatable snapshot.
`freshness` names `checked`, `finished`, committed total `ingested`, exact
result-scope `withoutVector`, and every required repository's state/count and
non-done reason. `withoutVector` includes partial plans, failed parts, failed
plans, absent plans, historical-model coverage and plans whose pinned tokenizer
cannot be verified. Such local coverage failures retain complete wording
access without decoding approximate plans. Branch/stash and disabled
versions are excluded. Documents-only scope counts its selected documents.

Results contain stable `id`, actual `repository`, `root`, relative `path`,
canonical qualified `address`, `name`, `origin`, `kind`, retained `lines` when
available, `score`, one-based `ranks`, and the first 240 characters as `preview`.
Checkout Markdown keeps document origin and its code-root address. Colliding
paths under code and artifact roots remain distinct. A readable `file` is an
absolute path checked within its actual configured root; missing, unavailable
or escaping files have an `unreadable` reason. The serializer also supports
index namespaces with stable IDs and no file. Applied overview sections now
compete as own-repository documents, with normal current-model vectors and no
code-only/shared inclusion or documentedIn bridge. Published summary nodes
also compete as own-repository documents through their retained index locations.

Each result and every `via`/`documentedIn` citation uses the same exact-version
`stale`, complete `staleReasons` with original source and intermediate path,
`heartwood`, and `dependencyCheck: {complete, faults}`. Citation identifiers and
canonical addresses select the same chunk as its own result. Missing checks,
no-fresh, pending source work and ref faults keep completion false; absent
stale marks alone never certify current claims. Completing mechanical checks
does not semantically verify the text. Scores remain comparable only within
one member reply and its ranking tier; the reply states the selected route.

Local classification bookkeeping shares the original freshness allowance.
It makes no Jev or reviewer calls. After successfully checked sources it updates
quiet-period eligibility and may apply a completed exact matching result through
the same canonical guards. `classificationCheck` reports whether this local work
was checked and complete, its pending stages and reused applications. Busy,
expired or unchecked sources remain explicit; `--no-fresh` performs none of this
work. Stored stale reasons keep their current classification evidence without
turning an incomplete dependency check into a current verification.

## Complete document links and undocumented code

Every code search result has `described: boolean`, computed from all direct
current disk declared/asserted document dependencies in either direction.
This flag is independent of the query, embeddings and configured shared
document selections. `documentedIn` retains its separate query-ranked,
current-model-covered, at-most-two citation behavior. Read a chunk to obtain
the complete `documents` array with each section, direction and edge kind.
Generated sections, relations and transitive connections do not describe code.

`mycel undocumented [--repo <name>] [--path <path>]... [--no-fresh]` lists code
without any such describing section. Select one enabled repository explicitly
or from its folder; organizations, multiple repositories and `--all` are
invalid. Paths are relative to its code root and select the named file or
all descendants of a directory. Repeated paths form a union; `src` does not
select `src-other`. Absolute paths and paths escaping the root are invalid.
The reply is `{repository, paths, chunks, freshness}`; each chunk is a canonical
Place, sorted by root, relative path and name. An empty list succeeds.

Before listing, the command uses the ordinary recursive search freshness check
under `search.freshness_seconds`, including pending/busy upstream reporting.
`--no-fresh` reads the current stored disk snapshot without writes. Branch and
stash-only code is excluded. It creates no dependency, model request or vector;
its only possible writes belong to the same ordinary freshness check.

<!-- sources:
mycel:@code/src/mycel/_document_links.py#document_links
mycel:@code/src/mycel/_undocumented.py#normalize_paths
mycel:@code/src/mycel/_undocumented.py#undocumented_from_store
mycel:@code/src/mycel/_search_store.py#_metadata
mycel:@code/src/mycel/_search_reply.py#search_reply
-->
