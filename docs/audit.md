# Auditing Origin claims

`mycel audit` tests the graph's Origin claims and retains findings for a person
to settle. Select one enabled repository, explicitly or from the current folder.
It uses the invoking configured clone's current indexed disk snapshot. It does
not ingest, embed, fetch, modify a source file or confirm freshness. Semantic
work requires complete current files matching that snapshot; ingest separately
when those files changed.

```sh
mycel audit --repo fixture --deterministic
mycel audit --repo fixture --path src --dry-run --k 5
mycel audit --repo fixture --path src --k 5
mycel audit --repo fixture --settle 13aab3df-54f1-59ed-9b46-9ea5627e2109 --reason 'Reviewed and accepted.' --by owner
mycel audit --repo fixture --deterministic --closed
```

Repeat `--path` for component-bounded code or artifact paths. `src` selects
`src/value.py`, but not `src-old/value.py`. Governing evidence may live outside
the selected paths. Multiple repositories, positional chunk arguments and
`--all` are invalid. Settlement takes an exact finding UUID, a nonempty reason
and optional actor; combine it only with repository selection.

## Deterministic findings

`--deterministic` reads the Index Store without source-file observations,
model credentials or model calls. It discovers these seven kinds:

| Kind | Condition |
|---|---|
| `unresting_requirement` | A current non-withdrawn requirement has no Origin dependant and no reasoned needs-nothing mark |
| `missing_origin` | A current code chunk has no Origin Link |
| `multiple_chapters` | A chunk has requirement Origins in at least two current files, identified by repository/root/path |
| `stale_chain` | A current chunk has mechanical stale reasons in the calling clone; the finding keeps the complete chains |
| `missing_discussion` | A current decision has no chat Entity URI in its Discussion metadata |
| `duplicate_id` | Parsed current rows repeat a human ID or UUID, including repeated-UUID parser faults; physical aliases count once |
| `missing_term` | An explicit Source Ref names an unresolved heading in an indexed file named `GLOSSARY.md` |

The glossary rule checks explicit references, rather than guessing terms from
ordinary prose. Duplicate and glossary findings own their exact diagnostic
text, including complete files needed to establish the fault. Ambiguous human
entity IDs remain resolvable by their separate UUIDs.

Ordinary audit also performs these rules. Every run lists retained open
findings, including earlier semantic findings in deterministic mode. A condition
that disappears is not automatically settled.

## Semantic questions and score changes

The three fixed questions have separate canonical versions and result caches:

| Question | Version | Labels in fixed order |
|---|---|---|
| Chunk conforms to one Origin | `mycel-audit-conformance-v1` | `conforms`, `nonconforming`, `insufficient_evidence` |
| Two Origins can govern one chunk consistently | `mycel-audit-consistency-v1` | `consistent`, `contradictory`, `insufficient_evidence` |
| A requirement admits materially different interpretations | `mycel-audit-ambiguity-v1` | `clear`, `ambiguous`, `insufficient_evidence` |

Audit examines every link method and confidence band. It asks conformance for
each link, consistency for each pair of distinct Origins, and ambiguity for each
current non-withdrawn requirement. Complete exact subject/Origin text and direct
governor/document-ancestor context form the input. Text is data, never model
instructions. Missing or changed inputs remain unresolved and authorize no effect.

A complete negative judgement opens a finding with its confidence, exact input
hash, validated stages and retained text evidence. Positive results open none.
With a reviewer configured, insufficient evidence, ties and confidence below
the configured floor route to it. Without one, the probability of the
question's negative label decides against its own floor:
`drifts.conformance_floor` and `drifts.consistency_floor` (0.7),
`drifts.ambiguity_floor` (0.8). A lower probability ends the pair without effect
and is kept as a judgement; oversized input remains `needs_llm_review`.
Audit reviewer successes require `confidenceScore` in [0,1] and citations drawn
from the request's exact evidence locators.

Only nonconformance lowers a score: `min(oldScore, 1 - confidenceScore)`, with
canonical decimal subtraction. Bands are asserted above 0.9, proven from 0.8,
inferred from 0.5, otherwise candidate; inferred/recovered model claims remain
capped at inferred. The method, statement author/time, dependency kind and pins,
verifications and stale marks remain intact. A lower score records who reviewed
it, when and the nonconformance outcome. Contradiction and ambiguity findings
change no link score. Audit never raises a score.

## Finite work and retained history

The existing `[drifts]` quiet period, candidate cap, attempt caps, exact byte
limits and monotonic command deadline apply. Audit executes one pair at a time,
within `at_once`. `--k` must be positive and bounds exact preparation attempts,
including unresolved ones, before evidence assembly. `capped: true` means work
remains outside that prefix. The fixed question order is conformance, consistency,
then ambiguity, with subjects and links ordered canonically within each question.
No background job or timer is installed.

Each configured clone keeps its own complete-file quiet observations. Inputs,
settings and model/reviewer identities are rechecked immediately before each
call and before final application. HTTP or child-process work holds no pass lock or
writing transaction. Only typed transient failures retry. Cancellation preserves
completed effects and ends outstanding leases. Unchanged complete results are
validated and reused without another model call, after the invoking clone's own
fresh guards and quiet period pass.

`--dry-run` returns proposed deterministic findings and bounded semantic
preparation, including eligibility and exact byte counts, with no state writes,
model credentials or calls. Combine it with `--deterministic` to avoid semantic
file observations as well.

Findings keep stable UUIDs for an exact observation and disputed claim identity.
A score/review update alone does not create a new observation. A person settles
with a nonempty reason; the record keeps actor, time and reason. Repeating the
same settlement is idempotent, and replacing it with a different reason is
refused. Settlement suppresses reopening and further score effects for the same
observation. Changed exact inputs or a new statement may produce another finding.
`--closed` includes settled history while running the requested audit; add
`--deterministic` for a report without model work.

The format-2 evidence store retains the newest 1,000 settled finding bundles per
repository, ordered by settlement time and full UUID. Every open finding and
in-flight request is protected. Retained findings protect their requests and
texts. Other ended, unreferenced semantic requests have a separate newest-1,000
bound. Collection removes only the expired record's ownership and unreferenced
evidence in that repository; shared evidence stays retained.

A semantic run is one step of a series, as in [recovery](recovery.md). Each step
keeps every judgement that changed nothing under its exact inputs and policy,
and the next step skips it until an input or the policy changes; a changed
floor alone reuses it. Repeat the command until the reply says
`complete: true`.

## Reply

`AuditReply` includes `repository`, `location`, `paths`, `deterministic`, `dryRun`,
`findings`, `newFindings`, `settled`, `selected`, `completed`, `reused`, `capped`,
`jevCalls`, `reviewCalls`, `errors`, `incomplete`, `pairs` and `status`. Semantic
selection also reports `attempted`, bounded `maxCalls`, and for the series
`remaining`, `complete` and `skipped`. Findings name their
UUID, kind, subject, disputed links, observation hash, source mode and first
observation time; semantic findings add confidence and exact input/result
evidence. Settled findings add actor, time and reason. Pairs report question,
eligibility, exact bytes, stage attempts and unresolved/failure reasons.

An open finding is ordinary successful output, with status 0. Debounce and an
unconfigured reviewer remain pending. Operational failures return 1, caller
interruption 2, retaining completed effects. A numbered Build records actual
finding, score and settlement mutations in activity. Dry-run, a repeated exact
result and an idempotent settlement create no mutation activity.

See [Origin Coverage](origins.md), [recovery](recovery.md),
[classification](classification.md) and the [command line](command-line.md).

<!-- sources:
mycel:@code/src/mycel/_audit.py
mycel:@code/src/mycel/_audit_semantic.py
mycel:@code/src/mycel/_classification_payload.py#AuditDecisionPayload
mycel:@code/src/mycel/_justify.py#confidence_band
mycel:@code/tests/test_audit.py
-->
