# Evaluation files and offline retrieval measurement

`mycel evaluate [--repo <name>] [--kind retrieval|drift] [--live]` reads one
enabled repository's configured evaluation file. Retrieval is the default;
`--live` is valid only for Drift. Omitted scope uses the current directory's
repository. Organizations, repeated selectors, `--all` and positional arguments
are unsupported. The command returns one evaluation report.

The file lives under the repository's resolved document folder. Set its relative
path with `repos.<name>.evaluation` in the owner's settings. Evaluation reads
that setting and never edits it. A missing setting is `settings`; an unreadable
file is `io`. Malformed UTF-8/TOML or invalid fields are `invalid_input`, naming
the file and field/line when available. Both sections are validated before
entering any execution adapter.

## Version 1 schema

```toml
schema_version = 1

[[query]]
text = "how does renewal decide"
expect = ["cellar:@code/src/auth/session.py#renew"]
only = "code"

[[drift]]
id = "source-deleted"
before = "RetryPolicy permits three attempts."
source_state = "deleted"
dependant = "Three retries are allowed."
expect = "needs_review"
critical = ["deletion"]
```

`schema_version` may be absent and otherwise must be integer 1. `query` and
`drift` are independently optional table arrays. Unknown fields are refused.
Retrieval text and expectation arrays must be nonempty text; `only` is `code`
or `docs` when present. Expectations retain their original spellings for exact
fault reporting. An empty selected section is valid. No query vector or model
call is made for it, and undefined shares are null.

Drift fixtures require string `id`, `before`, `dependant` and `expect`.
IDs must be unique. Expected outcomes are `still_supported`, `needs_review`,
`insufficient_evidence` or `unresolved`. A present source requires `current`,
including valid empty text; `source_state="deleted"` requires it absent.
Optional `context` is an ordered string array. `unavailable` contains unique
`baseline`, `dependant` or `context` entries and requires `expect="unresolved"`.
`unchanged=true` requires `still_supported`. Critical labels are `negation`,
`operator`, `permission` and `deletion`; they require `needs_review`, or
`unresolved` when required evidence is deliberately unavailable.

## Measurement substrate

The command prepares all query vectors first through the normal search query
planner and transport, preserving exact query text and wording-only fallback
reasons. Explicit retrieval evaluation supplies its own evaluation intent to
the credential and provider boundaries. If store dimensions differ from the
configured dimensions, it uses normal wording search without a provider call.
It then uses one
PostgreSQL-enforced read-only, repeatable-read snapshot under the shared format
guard. The adapter joins expectation resolution, eligibility, index fingerprints
and searches to that same transaction; each search receives `k=10` and
`freshness=False`. No mutation-lock rows, cache, vectors, pins, activity or
settings are written.

The producer reuses the ordinary candidate arms, current citation graph and
ranking. Every query borrows the same resolver and candidate snapshot; no
ordinary search command or freshness pass runs inside evaluation. Separate
read-only store-format and catalog inspections can precede this index snapshot.

<!-- sources:
mycel:@code/src/mycel/_evaluate.py#evaluate
mycel:@code/src/mycel/_evaluation_store.py#NormalQueryVectors
mycel:@code/src/mycel/_evaluation_store.py#StoreRetrieval
mycel:@code/src/mycel/_evaluation_store.py#normal_search
mycel:@code/src/mycel/_retrieval_store.py#candidate_snapshot_in_transaction
mycel:@code/src/mycel/_retrieval_store.py#CandidateSnapshot.ranked
mycel:@code/src/mycel/_search.py#prepare_query
-->

Expectations resolve through the central resolver in its read/result role:
class names select headers. A file/family, malformed/ambiguous reference,
missing chunk or ineligible result is a fault of the set. One faulty expectation
excludes its entire query from every recall denominator. Multiple spellings of
the same exact chunk count once. Expected positions remain one-based in the
unmodified top-ten reply; an absent expected chunk has no position.
Shared documents are selected through their current artifact-root aliases,
including files that retain a canonical code-root primary address. Expectations
and results still use one canonical chunk ID/version/address.

The report retains exact returned places, individual faults, recall at 3/10
overall and by route, wording-only count, Build/model/search-reply identity,
file hash, index generation/fingerprint, frozen effective-settings hash and
query-vector hash. Before/after compatibility requires these frozen inputs to
match; Build numbers may differ. No-index empty reports have null index
identities and cannot establish a comparable ranking measurement. Any
wording-only query prevents a claim of semantic-ranking quality.

## Non-live Drift evaluation

`mycel evaluate --repo <name> --kind drift` assembles each fixture into a
canonical decision and evidence bundle, then runs the production finite
classification runner with deterministic in-process Jev and reviewer stand-ins.
Expected labels score results only; they never enter a decision, adapter or
cache key. The default fixture store changes only this invocation's memory.
It opens no database, reads no provider credential and launches no model child.

The stand-ins compare tokenized before/current text, treat a complete deletion
as work to review, and report insufficient evidence for an empty dependant.
The configured confidence floor controls whether changed present sources
route through the reviewer stand-in. This gives a
repeatable exercise of evidence guards, routing and lifecycle behavior. The
report identifies the deterministic stand-in revision, marks simulated results,
leaves usage and cost null, and always reports `qualified=false`.

The runner processes the whole selected set in bounded batches, retains each
case's observed attempts and elapsed time, and reports stopped or unprocessed
cases explicitly. An interrupted run exits 2; other unfinished work exits 1.
A completed report exits 0 even when it is unqualified.
Missing baseline, dependant or context evidence stays locally
unresolved. No classification from this evaluation changes repository pins,
freshness or settings. `--kind drift --live` explicitly selects the configured
provider pipeline described below; its results are separate from this simulated path.

<!-- sources:
mycel:@code/src/mycel/_evaluation_drift.py#run_drift_evaluation
mycel:@code/src/mycel/_evaluation_drift.py#FixtureStore
mycel:@code/src/mycel/_classification_runner.py#run_classification
mycel:@code/tests/test_evaluation_drift.py
-->

## Current integration state

Strict schema validation, explicit dispatch and offline measurement are
implemented. Nonempty public retrieval uses the ordinary search producer.
Configured disposable-store checks use controlled query vectors with actual
candidate selection and ranking; the earlier injected-callback accounting
checks remain. The public command can also report an empty selected section.
An empty Drift report is unqualified and has no measured pipeline identity.

Only the selected kind runs, even when both file sections contain cases.
Nonempty non-live Drift evaluation uses the deterministic fixture pipeline
above. MYC-13.11 covers retrieval and selected-kind dispatch; provider-live
qualification remains a separate explicit operation. Each on-demand MYC-4.25
ranking evaluation must execute against the selected immutable implementation;
a saved receipt cannot supply its live proof. No ranking or grouping constant
changed in this work.

<!-- sources:
mycel:@code/src/mycel/_evaluate.py#evaluate
mycel:@code/tests/test_evaluation_retrieval.py
mycel:@code/tests/test_evaluation_store.py
mycel:@code/tests/test_evaluate_cli.py
-->

## Explicit provider qualification

`mycel evaluate --kind drift --live` uses the same complete canonical fixture
store and finite classifier runner, with the actual configured Jev model and
independent reviewer command. It does not connect to a corpus store or persist
fixture lifecycle state. Missing reviewer configuration/executable or an
unavailable Jev credential yields an unqualified report before paid cases are
sent. Missing required fixture evidence stays local unresolved with zero calls;
a complete deletion tombstone remains eligible.

The selected set runs in bounded candidate batches under the configured
concurrency, per-stage attempt limits and per-batch deadline. Cancellation
retains unprocessed cases, ends requests/reviewer groups through the production
runner and makes qualification inconclusive. The reply includes exact model,
question/Choice/routing identity, reviewer command hash and immutable adapter,
instruction and environment revisions, per-case probabilities and categorical
results, actual attempt records, monotonic local elapsed time and separately
reported stage usage. Missing or partial total usage and all unknown costs stay
null. Elapsed fixture lifetime includes scheduling and is not labelled provider
latency; individual attempt records contain the observed stage duration.

Coverage floors count distinct semantic before/current/dependant/context and
availability combinations, excluding IDs and labels: at least 200 distinct
pairs, 50 critical covering negation/operator/permission/deletion and 50
unchanged/cosmetic. Conflicting duplicate ground truth
cannot qualify. No critical work may finish incorrectly as `still_supported`.
On at least one common routed adjudicated case the reviewer must have no more
critical misses or wrong labels than Jev and must strictly improve wrong-label
or unresolved count. A failed/unprocessed case or changed returned identity
prevents qualification. The report separately retains meaningful misses, unnecessary work, support
precision and escalation rate, overall and by critical category, unchanged/
cosmetic and other cases. Every share names its population and denominator; a
zero denominator is null. Critical tags may overlap, and repeated observations
remain diagnostics while qualification coverage counts distinct semantics.
No threshold, pin, source or settings value is retuned.

`profileFingerprint` describes the exact configured provider components;
`reportFingerprint` describes this versioned measured report. Neither is a
same-Build acceptance proof. Explicit acceptance must execute named live/eval
checks and retain the genuine in-process `OnDemandProofs` object bound to that
immutable Build and registry. A JSON report cannot be reloaded into such a
proof. Automatic gates continue to exclude live/eval checks. The internal
on-demand helper is prepared in `_provider_checks.py`; it is not invoked by
normal evaluation, import or automatic discovery, and registers no requirement
claim in this private preparation.

No 200-pair labelled release set or configured independent reviewer profile is
provided by these code changes. This isolated source preparation executes no
provider call and establishes no live qualification or runtime acceptance.
Standing operator authorization does not replace the concrete corpus, profile,
budget and genuine result checks required for any later explicit operation.

<!-- sources:
mycel:@code/src/mycel/_evaluation_live.py#run_live_drift_evaluation
mycel:@code/src/mycel/_provider_qualification.py#qualify_profile
mycel:@code/src/mycel/_provider_checks.py#run_provider_checks
mycel:@code/tests/test_provider_evaluation.py
-->


## Prepared provider deployment consumer

The internal development seam `_provider_deployment.prepare_deployment` reads
one exact reviewed explicit live report and the already validated labelled set.
It requires a matching current Jev model, question, Choice order, routing policy,
confidence floor and reviewer provider/model/revision/command/instruction/
environment identity. It recomputes coverage floors and quality diagnostics,
rejects missing, changed, incomplete, empty-routed or failing measurements, and
retains the whole report with category-separated misses and unnecessary work,
support precision, escalation, reviewer comparison, usage, time and cost.
Unknown usage or cost remains unknown. The consumer makes no model call and
changes no source, settings, pin or store value.

The deployment caller must keep the genuine operation receipt for that single
explicit group run beside the returned component record. A report hash binds
retained bytes; its content alone cannot establish that a provider was called.
Reusing that exact component report after an unrelated Build change does not
make a fresh live check or same-Build requirement proof. Any semantic pipeline
identity change requires a new explicit qualification. This deployment review
remains separate from ordinary automatic working-Build qualification, which
uses no real model quota. The prepared consumer adds no public command or
configuration key and registers no live claim.

<!-- sources:
mycel:@code/src/mycel/_evaluation_live.py#run_live_drift_evaluation
mycel:@code/src/mycel/_provider_qualification.py#qualify_profile
mycel:@code/src/mycel/_provider_checks.py#run_provider_checks
mycel:@code/tests/test_provider_evaluation.py
mycel:@code/src/mycel/_provider_deployment.py#prepare_deployment
mycel:@code/tests/test_provider_deployment.py
mycel:@code/tests/test_provenance_conformance.py
-->


## Same-process explicit provider group and deployment check

The group caller explicitly executes146 `run_provider_checks` once and passes
its original returned `OnDemandProofs` and reports objects directly to
`run_provider_deployment_checks`. The147 consumer never invokes that producer,
so invoking it cannot silently spend again after146 has already run. It
executes one named `MYC-14.22` live check over those supplied actual objects,
validating the original proof class, complete registry/implementation identity,
all three successful named provider checks, same Build/repository, whole report
and current settings/reviewer pipeline. It makes no provider, credential or
store call and loads no report file.

The proof dataclass and plain reports dictionary do not authenticate their
own origin. The trusted same-process group caller must supply the actual
objects and retain genuine operation provenance; its full code/result review
establishes that origin. A self-comparison cannot prove it, and this helper
makes no such claim. The separate `prepare_deployment` retained-report seam
provides component provenance only, never a reconstructed same-Build proof.

The consumer returns the original provider proof object alongside its newly
executed consumer proof object, as a sequence for the existing coverage API.
A failed provider object or report causes a genuine failed consumer check,
retaining earlier reports without another dispatch or retry. No proof object
or result row is fabricated from serialized evidence. Automatic Build
discovery and non-live evaluation never call this live consumer.

The isolated source preparation has executed no new test, store fixture or
provider operation. Actual146 group reports,147 live evidence, qualification,
application and task acceptance remain unknown. The94-case research corpus
is not the required200-case qualification set. Standing operator authorization
does not replace immutable corpus/profile/budget guards and genuine results.

<!-- sources:
mycel:@code/src/mycel/_provider_deployment.py#run_provider_deployment_checks
mycel:@code/src/mycel/_provider_checks.py#run_provider_checks
mycel:@code/src/mycel/_coverage.py#run_on_demand_checks
mycel:@code/src/mycel/_coverage.py#run_checks
mycel:@code/tests/test_provider_deployment.py#SameRunProviderDeploymentCallerTests
-->
