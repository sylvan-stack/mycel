# Exact-pair Drift work

A Drift holds unresolved work for one exact dependant version. Mechanical
detection opens local work for every changed source or related pair, removed
source, broken reference and upstream stale reason. Three changed sources on
one dependant produce one Drift with three pair reasons. Opening work starts
no classifier, reviewer, embedding or generation call.

Each reason has its own active input, categorical classification state and
retained attempts. The states are `pending_debounce`, `pending_jev`,
`needs_llm_review`, `complete` and `error`. Complete judgements are
`needs_review`, `insufficient_evidence` and `still_supported`. Pending,
review, insufficient evidence and error work remain visible. Escalating to a
reviewer retains the original Jev evidence alongside the review outcome.

Only a complete `still_supported` judgement closes the selected direct pair's
work. Other source, related, broken reference and upstream reasons remain
open. Detection preserves earlier stale-reason classification evidence; only
an applicable explicit result publishes a new annotation. A classifier or
reviewer result never clears a stale mark, advances a baseline pin or writes
a verification. Explicit confirmation and an authorized affected-section
edit keep their existing freshness rules.

A later exact source or dependant input replaces the active pair input and
retains the earlier attempt as history. Earlier support cannot suppress the
new input. Returning the source to its pinned comparison state closes only
its source-change or removal reason. Removing a declaration or assertion
closes only its corresponding work. A formatting or recognized rename
transition that inherits its baseline carries unresolved work forward.

A missing source is a valid removal state with retained pinned evidence.
Failure to read a live source is an unresolved error. Broken, disabled and
unregistered references stay open without a guessed edge or model call.
An upstream stale reason stays open even when the selected direct source
receives support. Heartwood closes work under its exemption. Generated text
uses regeneration work and remains ineligible as a declared/asserted source or
relation target.

Off-disk versions retain inactive work with their locations. Removing every
location closes the old version's work as `version_removed` history and
retains its exact evidence independently of searchable chunk rows.

These are internal transaction-bound lifecycle APIs. The [classification
evidence producer](classification.md) supplies canonical complete requests,
quiet-period state and fresh guards. The Jev and reviewer adapters execute
bounded work through public `classify`; the writer retains closed history under
the bound described below.
The public provenance reports below read this retained work without running it.

`DriftStore.sync_in_transaction(settings, repositories, ...)` joins an existing
guarded writing transaction after mechanical detection or an authorized
dependency change. It commits nothing and acquires no operation guard. The
producer supplies its exact affected versions, pending observations and
authorized closure event. Collection closes disappearing versions before
deleting their searchable rows. Store format 3 retains the existing Drift table
and independent permanent `drift` evidence owners.

`DriftStore.reconcile(settings, repository)` is a finite internal offline
projection over already indexed inputs. `record_classification` accepts one
Drift ID, reason ID and exact `pairHash`, plus a categorical result and
validated stage metadata. An obsolete reply recorded during reconciliation
remains an attempt and has no effect on current work. If live input changes
during final annotation publication, the sink refuses the write and rolls
back the transaction. The lifecycle `pairHash` binds the local retained
pair evidence; the optional `canonical_input_hash` records the separately
assembled canonical classification request. It does not substitute for that
request's context, question, model or policy guards.

`DriftStore.list(repository, closed=False, all_versions=False)` reads one
committed snapshot and returns Drift records, exact locations and separate
generated regeneration entries. It changes no work, evidence, activity or
freshness rows. Public report handlers use the same retained work and locations
and add the complete status counts.

## Read-only provenance reports

```sh
mycel drifts --repo cellar
mycel drifts --repo cellar --closed
mycel drifts --repo cellar --all-versions
mycel drifts --repo cellar --closed --all-versions
mycel stale --repo cellar
mycel status --repo cellar
```

`drifts` lists current on-disk open work. `--closed` also includes closed work
for the current versions. `--all-versions` includes retained off-disk versions;
combining the flags also includes closed removed-version history. Each inactive
record keeps its explicit retained branch or stash locations. A removed version
has no searchable locations and keeps its closure and exact evidence in history.

Every reply contains separate `counts.work` and `counts.pairs` maps, each with
`currentOpen`, `currentClosed`, `inactiveOpen` and `inactiveClosed` counts. Three
changed sources on one dependant are one work item and three source pairs. An
exact source-pair key is the dependant version, dependency ID and canonical
classification input hash, or the local pair hash before a complete input was
assembled. Multiple reasons for a dependency remain distinct when their exact
inputs differ. Pair openness follows its active reason; a supported pair can be
closed while another pair keeps the dependant's work open.

`counts.stages` counts current retained pair stages; `inactiveStages` reports the
corresponding off-disk stages separately. `judgements` and `inactiveJudgements`
count completed outcomes, including `still_supported` evidence on closed pairs.
`unresolvedFaults` counts current active reference, baseline or execution faults;
`inactiveVersions` counts retained versions away from disk. Generated summaries
remain separate `regeneration` work. These counts cover all retained work,
independently of which listing flags were selected, and omit obsolete attempts
stored in history.

`stale` returns each current disk or generated-index chunk with every stored
reason, direct reasons before propagated reasons. Sources use canonical
repository/root/path addresses; each propagated reason retains the original
source and its ordered path through intermediate chunks. A reason's exact
classification stage, input hash and model evidence remain available even after
`still_supported` has closed its Drift pair. The stale mark stays in place.

`status` counts current chunks and stale chunks, valid unresolved reference
occurrences, references invalid because their target repository is unregistered
or disabled, and all reference faults. Declared source and related reference
occurrences participate; retained branch-only declarations do not inflate the
current counts. It also returns the separate Drift work, pair and stage counts.
`refs --unresolved` already supplies the detailed fault records and root-aware
ambiguity candidates behind those counts.

Reports take one committed read-only repeatable-read snapshot for the selected
repositories. They do not scan or ingest files, retry reference resolution,
reconcile pending stages, allocate repository locks, collect evidence, spawn a
reviewer or call a provider. A quiet period expiring is visible only after an
authorized local projection or explicit classification has updated the stored
stage. Listing work cannot start execution or advance its freshness baseline.

## Closed history and protected evidence

Writing transactions retain the newest 1,000 closed bundles per owning
repository, ordered by closure time and then full Drift identifier. Superseded
source or canonical request inputs become independent closed diagnostic bundles
with obsolete disposition. They retain complete decision bytes, snapshots,
stage attempts and original closure provenance. Repeated identical inputs attach
to the same retained bundle rather than copying its text into new history owners.

Open work, current suppression records, live baselines, verification history and
in-flight request evidence remain protected. Such protection can exceed the
closed-history bound. Pruning removes eligible closed records and their metadata
references together; it collects a snapshot or manifest only after its last
owner reference disappears. A late obsolete stage result remains attached to its
exact archived input until the attempt has ended. Report commands and activity
pruning do not run this collector.
