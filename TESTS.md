# Tests: mycel

Only the top-tier cases below are active. They may be selected when useful during implementation; running tests after every change is not required. Writing, restoring or running mid-tier tests requires a separate testing task explicitly requested by the owner. Do not write or restore low-tier tests.

[Mid-tier descriptions and justifications](MID_TIER.md) · [Complete inventory and tier justifications](docs/test-inventory.md) · [Machine-readable inventory](test-tiers.json)

Reviewed revision: `a80c617dd535d6e8142ce940ff73b7825f7e6c6c` (28 October 2026), plus the preceding local pruning changes. No tests were run for this reset. On 29 October 2026 SYL-315 added two individually reviewed top-tier ingest cases.

## Selection and limits

8 active Python definitions and 0 active standalone programs; 1785 commented Python definitions. Also disabled: 0 named Node cases, 0 custom scenario functions and 2 standalone check programs. 1 broad entry points explicitly refuse. 26 low-tier cases remain removed from the prior review. These categories overlap in execution and must not be added into a runtime suite size.

Top-tier cases were individually read for the failure they observe. The remaining mid-tier labels are provisional execution decisions, not a claim that thousands of tests have passed a complete semantic review. Reassess value before restoring any of them. A browser program may contain many assertions; it is inventoried as one indivisible program, not as one asserted behavior.

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

Case bodies are separated into [`tests/top/`](tests/top/) and [`tests/mid/`](tests/mid/). The former mixed test modules retain shared fixture classes, helper functions and imports at their established paths, with no inventoried test methods. This preserves existing subprocess paths, patch targets and fixture imports without copying helpers into both tiers. Original check entry points retain their refusals.

## Running a selected top-tier case

Select an exact method when it resolves a concrete uncertainty; no run is required after an edit. The new module names begin with test_top_ so they cannot shadow the shared fixture modules. Do not run whole folders or discovery as a substitute. Original prerequisites, skips and environment limitations still apply. A focused result is not full qualification.

The fixture-aware runner defaults to tests/top and also imports shared support from tests. Store cases still require an explicit disposable-store settings file.

```sh
PYTHONPATH=src python scripts/run_checks.py --select test_top_source_refs.SourceAddressTests.test_double_encoded_sequences_remain_literal_after_one_decode
```

## Mid-tier review and restoration

[MID_TIER.md](MID_TIER.md) describes every retained mid-tier entry and its existing reason, identifies provisional classifications and explains restoration. Only a separately requested testing task may restore or run these sources. Keep the source in the mid folder; restore only the selected imports, class headers and bodies, update the inventories, and return the source to comments afterward unless the owner says otherwise. Broad entry points continue to refuse; repairing a qualification workflow requires its own explicit testing task.

Layout revision: `faff2f949f25e3c486cf314e881a83a5a689a1ef`. No tests were run for this reorganization. Previous identifiers and source lines are retained in test-tiers.json. Indexed Origin relocation and ingest remain deferred; moving files supplies no new runtime proof.
