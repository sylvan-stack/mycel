# Jev dependency decisions

The internal Jev adapter handles one already prepared eligible dependency pair
per attempt. It sends the complete canonical decision to the pinned TypeSafe
model and returns a categorical result or complete input for independent review.
The [reviewer adapter](reviewer.md) now executes the independent handoff.
The finite `classify` runner owns candidate selection, retries and guarded
application. The historical v5 live qualification failed; its reports remain
failed. The revised routing contract requires fresh qualification before
deployment.

`JevRequest(decision).body` contains one `state`, the exact decision model and
one `dependency` Choice question. The packaged instruction and Choice criteria
are transmitted in their accepted order: `needs_review`,
`insufficient_evidence`, `still_supported`. The state includes every pinned,
current, dependant, governor and ancestor text/manifest plus removal or away
state. The adapter applies no edit-size gate. The endpoint, bearer
authentication and response shapes follow the [official TypeSafe API](https://docs.typesafe.ai/api).

The adapter uses the accepted `jev-1.13.0` default or the exact version already
bound by `DecisionPayload`. Moving aliases fail canonical preparation. The
returned model must equal this exact version. `JevClient` acquires only the
`mycel` / `jev-api-key` item from the login Keychain; it does not consume
embedding credentials, environment keys, configurable endpoints or Arbol
code/instructions. The provider secret is revealed only at the in-process
fixed HTTPS boundary. Redirects, ambient proxies and TLS key logging are absent.

`JevClient.classify(decision, deadline=..., before_call=..., cancelled=...)`
performs at most one provider request. Its caller owns the exact stage lease
and supplies a fresh `before_call` guard that raises when inputs, eligibility,
settings or invocation liveness have changed. The guard runs before Keychain
access and again before HTTP transmission. The caller enters
`ClassificationStore.stage(..., stage='jev')`, checks its allowed result,
keeps that context alive through the attempt, and uses
`ClassificationStore.apply` for later guarded effects. Independent review
requires its own `stage='review'` check. This module writes no Drift result,
stale mark, baseline pin or verification.

`JevLimits.from_settings(settings)` reads the configured attempt timeout and
complete body cap, initially 10 seconds and 24,000 UTF-8 bytes. An absolute
monotonic invocation deadline clamps the attempt, including credential access,
request transmission, response reading and validation. Cancellation closes
the retained connected socket even when an HTTP response detaches it from the
connection. Delayed DNS/TLS work checks the stopped flag before it can send.
The adapter caps each HTTP response at 1 MiB. Its decimal arithmetic uses all
required places with a 1 MiB precision ceiling; an encoding requiring more
precision is terminal `provider_result_invalid`, never a rounded support result.

Validation requires exactly the dependency Choice answer, the three known
probability keys, finite numbers in [0,1], a sum within 0.000001 of 1, a
chosen maximum label and reported provider confidence finite in [0,1]. Compute
canonical routing confidence exactly as `(3 * p_top - 1) / 2` from those unchanged
probabilities. Do not renormalize the distribution, clamp or round the result.
An out-of-range canonical confidence is `provider_result_invalid`. Preserve
`reportedConfidence` separately and retain exact agreement plus the signed
`reported - canonical` difference; disagreement alone is diagnostic. No provider
rounding rule or confidence-difference tolerance is inferred. Duplicate JSON
keys, another answer type, wrong model, missing fields, malformed distributions
and invalid usage counts remain failures. Decimal arithmetic preserves the
probability-total boundary and exact routing comparison. The [vendor confidence definition](https://docs.typesafe.ai/confidence)
explains the distribution statistic; it is not an independently verified
probability of a correct Mycel judgement.

Every valid retained `JevResponse.as_dict()` includes mandatory `exactDecimals`:
`probabilities` maps exactly the three known labels to decimal strings, while
`confidence`, `reportedConfidence` and `reportedMinusCanonical` retain the exact
validated or derived decimal values as strings. This is decimal-value evidence;
it does not preserve or claim the original JSON numeric lexemes or wire bytes.
Existing numeric fields remain display projections and may round a value such as
`0.50000000000000005` to `0.5`. `confidenceComparison.matches` still uses exact
Decimal equality. Routing, ties and the floor use exact values; retained-report
qualification, Jev-only baseline reconstruction and deployment validation must
use the companion strings and validate their formula/range/distribution and
display-projection consistency. Missing or inconsistent evidence cannot qualify;
no constructor or confidence-floor tolerance is relaxed.

`JevOutcome` retains the exact input hash, returned model/distribution/usage,
canonical `confidence`, separately reported confidence and its comparison, the
configured canonical confidence floor and `mycel-drift-routing-v2` identity.
Compare the exact canonical statistic with the unchanged 0.7 floor; equality
is sufficient. Lower canonical confidence, any tied maximum or
`insufficient_evidence` returns `needs_llm_review`. Because reported confidence
is diagnostic, a reported value below 0.7 may take the Jev path when canonical
confidence reaches 0.7 and the other routing conditions permit it. A complete
high-confidence `needs_review` or `still_supported` supplies only that exact
pair's categorical judgement to the guarded sink. Mechanical staleness is
preserved by that sink. Changed routing identity invalidates old cached results
and requires fresh versioned qualification; it does not repair failed history.

When the complete serialized body exceeds its cap, Jev is bypassed before
credential acquisition with `jev_input_too_large`. Recognized explicit context
refusal codes in a 400/413/422 response also route review:
`context_length_exceeded`, `max_context_length_exceeded`, `input_too_long` and
`too_many_tokens`, either at top level or in `error.code`. The vendor's public
API documents generic 422 validation failures without a guaranteed context
error envelope; these codes are the adapter's conservative compatibility
allowlist, not a verified live-provider shape. Other 422 responses remain
terminal `invalid_request`; arbitrary diagnostic words do not trigger review.

`outcome.reviewer_handoff(timeout_ms=..., max_input_bytes=...)` builds the
existing protocol-1 `ReviewerRequest` from the identical complete decision.
Its budget counts canonical JSON plus the transmitted LF. No required text
is truncated. Missing reviewer configuration retains the decision as
`reviewer_unconfigured`; an oversized reviewer request retains it as visible
`review_input_too_large` unresolved work. This handoff starts no reviewer and
passes no Jev credential to a process.

`JevFailure` exposes safe typed diagnostics. Authentication, invalid requests
and invalid results are terminal. Connection, timeout, HTTP429 and HTTP529/5xx
produce retryable stage faults with a finite optional `Retry-After` delay.
The adapter does not retry or sleep. The finite classifier must honor delays
only when they fit its remaining stage/invocation allowances. Raw provider,
Keychain and OS diagnostics are never included in results.

Automatic proofs use public fictional credentials and service/socket stand-ins.
They must cover fixed request/order/identity, tiny changes and rewrites, exact
canonical floor equality, disagreement diagnostics including reported below-floor
values, low-confidence/tie/insufficient routing, probability-total tolerance
edges, canonical out-of-range rejection, terminal malformed replies, complete
body/reviewer caps, context refusals, call guards, changed-policy cache identity,
deadline/cancellation and detached-response cleanup. These controlled proofs
do not establish real provider qualification.
