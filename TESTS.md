# Tests: mycel

All test work, including top-tier cases, requires a separate task explicitly requested by the owner. Implement and polish code first; only the owner decides when it is ready for tests. Do not write, edit, maintain or run tests during implementation. Keep existing source in its documented state and low-tier examples commented at file ends.

[Mid-tier descriptions and justifications](MID_TIER.md) · [Complete inventory and tier justifications](docs/test-inventory.md) · [Machine-readable inventory](test-tiers.json)

Reviewed revision: `560e2e2b1623066240ebd128bfa1e552f0a4f25f` under SYL-327 (29 October 2026). No tests were run.

## Selection and limits

8 top-tier inventory entries and 135 mid-tier entries are available after the higher-bar review. 1653 low-tier entries were removed under SYL-327. Definitions, scenarios, programs and entry points overlap; this is not a runtime suite count. Top-tier bodies are unchanged. Retained mid-tier sources remain uncommented.

## Active top tier

| Exact selector or program | Why this case earns a place |
| --- | --- |
| [`test_top_ingest.IngestStepStoreTests.test_a_series_completes_while_a_file_changes_before_every_step`](tests/top/test_top_ingest.py#L8) | Documented SYL-315 regression of SYL-289 run 3: while another agent edited a file before every step, each step that wrote it started the refresh of unchanged files again, so a stepped pass never completed. Edits a file before every step of a series and requires the pass to complete within a bounded number of steps. |
| [`test_top_ingest.IngestStepStoreTests.test_a_refreshed_file_resting_on_a_written_file_is_refreshed_again`](tests/top/test_top_ingest.py#L29) | Non-obvious edge of the SYL-315 fix: a file the refresh already passed rests, through a Source Ref, on a section a later step writes. Requires that step to refresh it again, and the finished series to leave the dependency, edge, relation and stale rows exactly as one whole pass does. |
| [`test_top_recovery.RecoveryStoreTests.test_edit_during_final_audit_rolls_back_the_origin_claim_and_edge`](tests/top/test_top_recovery.py#L14) | Edits source during the final audit callback after a provider result exists. Requires transaction rollback of both the origin claim and its dependency edge, preventing publication against changed evidence. |
| [`test_top_recovery.RecoveryStoreTests.test_a_pair_in_error_keeps_the_step_reply_and_closes_its_activity_failed`](tests/top/test_top_recovery.py#L26) | Documented SYL-289 regression: a provider error previously closed activity as refused without an error and lost the recovery reply. Checks both the emitted partial-progress reply and persisted failed activity. |
| [`test_top_relation_occurrence_regressions.RelationOccurrenceRegressionStoreTests.test_mixed_closed_and_unclosed_same_ref_pins_valid_occurrence_and_reports_only_invalid_fault`](tests/top/test_top_relation_occurrence_regressions.py#L12) | Places valid and unclosed declarations of the same source in one document. Checks that occurrence-local validity creates one legitimate pin, reports only the malformed occurrence as faulty, and leaves reads non-mutating. |
| [`test_top_relation_selection_regressions.RelationSelectionRegressionStoreTests.test_same_literal_short_method_ref_cannot_redirect_existing_pin_to_unrelated_place`](tests/top/test_top_relation_selection_regressions.py#L11) | Replaces a previously pinned class with an unrelated class exposing the same short method name. Requires publication refusal and unchanged persisted relation state instead of silently redirecting the pin. |
| [`test_top_source_refs.SourceAddressTests.test_double_encoded_sequences_remain_literal_after_one_decode`](tests/top/test_top_source_refs.py#L11) | Uses double-encoded separators, traversal spelling and a name delimiter. Requires exactly one decode and a stable canonical address, protecting literal names from accidental reinterpretation. |
| [`test_top_store_acceptance.ProductStoreTests.test_exact_utf8_nul_bytes_projection_and_hash_guards_roundtrip`](tests/top/test_top_store_acceptance.py#L14) | Regression for quadratic dense-NUL projection: 100,000 NUL bytes must project within a finite SQL deadline. Also checks byte-preserving storage and independent database constraints on hashes and projections. |

## Layout and shared support

Case bodies are separated into [`tests/top/`](tests/top/) and [`tests/mid/`](tests/mid/). The former mixed test modules retain shared fixture classes, helper functions and imports at their established paths, with no inventoried test methods. This preserves existing subprocess paths, patch targets and fixture imports without copying helpers into both tiers. Compatibility entries preserve original package and resource paths while loading the mid-tier implementation. Product-side test APIs load it only when invoked and refuse if the test source is absent.

## Running a selected top-tier case in an owner-requested testing task

Select an exact method when it resolves a concrete uncertainty; no run is required after an edit. The new module names begin with test_top_ so they cannot shadow the shared fixture modules. Do not run whole folders or discovery as a substitute. Original prerequisites, skips and environment limitations still apply. A focused result is not full qualification.

The fixture-aware runner defaults to tests/top and also imports shared support from tests. Store cases still require an explicit disposable-store settings file.

```sh
PYTHONPATH=src python scripts/run_checks.py --select test_top_source_refs.SourceAddressTests.test_double_encoded_sequences_remain_literal_after_one_decode
```

## Mid-tier execution

[MID_TIER.md](MID_TIER.md) lists the descriptions, tier reasons and review status. The source is now uncommented and stays that way. Writing or running it still requires a separately requested testing task. Do not run tests automatically after edits or merges. Inspect prerequisites and indirect calls before invoking a program or qualification entry point. A focused result is not full qualification.

For a Python method, use the same fixture setup as the top tier, put the mid folder on PYTHONPATH, and select `test_mid_<module>.Class.test_method`. Mycel's fixture-aware runner accepts `--tests tests/mid --select test_mid_<module>.Class.test_method`; store cases require explicit disposable-store settings. Archived scenarios and programs retain their original compatibility entry paths.

Restoration under SYL-326 used static checks only. No tests, Builds, provider calls, Origin migrations or corpus ingest were performed. Original prerequisites and environment limits still apply.

## Qualification after SYL-327

The source runner continues to require exact selections. Reduced selections are not historical full qualification: `tests/qualification-status.json` records that a separately requested qualification task must review the requirement mapping before a complete run can write the named checks again. No tests, Builds, provider calls or owner-store operations ran during this pruning.

The review used an AST census of calls, assertions and patch boundaries, followed by targeted inspection of retained case bodies and fixtures. This is risk-based retention, not a runtime proof that the removed coverage is redundant.

## Builds

Since SYL-329 (29 October 2026) a Build runs the top tier only (MYC-D73). Its automatic gate selects every `unit` and `store` check under `tests/top/` and no mid-tier check, and refuses when `tests/top/` has no test source or a top-tier source is commented. The mid tier runs only when the owner asks for a mid-tier run. A passing top-only Build is not full qualification and does not rewrite the named checks.

## Owner-controlled testing and archived examples — SYL-330

All test work is separate from implementation, including top-tier regressions,
fixtures, snapshots, classification, archival maintenance and runner changes.
Only the owner decides readiness and requests the testing task; do not create
one autonomously or widen implementation into testing. A test-running Build
also belongs to a separately requested testing/Build task; its gate stays intact.
A test review, writing or archival task does not itself authorize execution.

Read the retained cases and the `LOW TIER — DO NOT ENABLE OR RECREATE` footers
before adding related tests. They preserve rejected historical source, reasons
and revisions, so obvious or redundant checks are not generated again. All
archived lines are comments, including imports and registrations. They add no
runnable coverage. Re-admission needs distinct new evidence and owner-requested
test work; a testing request alone does not make low-tier cases useful.
