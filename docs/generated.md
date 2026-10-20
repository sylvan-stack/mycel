# Generated provenance and regeneration work

`GeneratedPublicationStore.publish_in_transaction(settings, invocation, lease,
chunk_id, place, level, metadata, guarded_repositories)` is the internal store
hook for successfully produced summary text. `place` is one canonical
repository-owned `@index/summaries#level/number` address, with level 1–5 and a
positive number. Every member belongs to that repository; higher summaries use
only strictly lower levels. It accepts an exact live connection-bound request
lease with a complete UTF-8 nonempty response, and publishes the entire response.
It starts no writer or embedding call.

The caller holds `checked_store`, pass/removal guards for every source,
publication and affected downstream repository, and one atomic transaction.
The hook acquires no operation guard, opens no savepoint and commits nothing.
It rechecks effective settings, exact indexed member identities/versions/bytes,
physical source files and bindings, and selected generated-member state,
evidence and transitive freshness. Failed requests, missing responses, inactive
or forged leases, changed inputs and stale generated members produce no live
text or pins when the error escapes the transaction. A refused confirmation
cannot publish or repin generated text.

One publication writes the exact response version, current index location,
compatible `PublishedSummaryState` version 1 and one `generated` dependency
per ordered request member. Generated pins coexist with declared and asserted
rows between the same ends. Files and ordinary assertion commands cannot
create generated rows. Store format 3 retains these tables and verification
ownership from format 2 without changing this publication contract. Independent
permanent `generated` owners have no invocation foreign key and retain both request/completed manifests and all full/sent
member, prompt, request and response snapshots. Each generated dependency's
`mycel-generated-pin-v1` state identifies its complete request manifest, original
request manifest, member ordinal/identity and dependant identity. All siblings,
owner references, produced bytes and current summary membership must agree.

The hook mechanically recomposes current disk and index dependencies in the
same transaction. A changed document member compares its supported normalized
body hash, while a generated summary member compares complete exact text.
Missing sources retain readable places and exact old evidence; reappearance
joins the pin by surviving logical identity or its retained natural place.
Detection never repins. Reasons pass through generated levels, preserving
original source and path. A successful same-response regeneration clears
answered direct/upstream reasons and recomposes its parents; a changed response
makes parents stale against their unchanged generated pins. The file metadata
exception `generated: true` remains distinct from index-generated summaries.

After caller-owned vectors, other nodes or audit callbacks, call
`verify_in_transaction()` immediately before committing. It rechecks exact
source/settings/invocation inputs, output index location and metadata, permanent
membership/evidence, generated edges and the detector's final physical and
evidence signature. The detector signature includes both request/completed
manifests, all referenced snapshots, owner invocation and generated-state rows.
Callback removal, rebinding or corruption rolls back the entire transaction.
One publisher instance can compose multiple outputs; each publication refreshes
the detector for its own additional prospective rows, and final verification
checks all produced outputs.

`GenerationEvidenceStore.retain_in_transaction` and
`retain_response_in_transaction` adopt already prepared exact request/response
evidence under the caller's guarded transaction without calls or commits.
This permits an upper preproduced capture to refer to lower outputs in the
prospective transaction. The existing `retain`/`retain_response` API still owns
its short private commits before/after external generation. Failed aggregate
publication also rolls back prospectively adopted higher evidence. A temporary
lease may be released after successful commit; it never owns the published pins.

Summary status and regeneration plans report this mechanical work read-only.
They verify real request membership and evidence, retain missing members, order
work from lower levels upward and block parents whose generated members remain
stale. No semantic classification, model call or duplicate semantic Drift is
created. Missing/corrupt generated evidence remains stale or pending rather than
being treated as fresh. Confirmation of an authored source recomposes generated
descendants while preserving their independent direct reasons and pins.

The public build consumer now retains private request/response leases before
external calls, reserves exact lower-member identities without searchable rows,
embeds actual completed levels and replaces the complete tree in one guarded
transaction. Its final verification follows vector and mutation-audit writes.
It transfers successful evidence to permanent generated owners and releases
private leases in that transaction. Failed or interrupted staging preserves the
old tree and releases its owning leases. Empty replacements keep versioned set
metadata without searchable summary nodes. Public `summaries regenerate`
repairs stale nodes in level order, while `summaries remove` deletes the set
and releases only evidence with no surviving owner. The hook
alone supplies none of the public build's grouping, service calls or vectors.
