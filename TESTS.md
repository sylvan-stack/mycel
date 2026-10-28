# Tests: mycel

Only the top-tier cases below are active. They may be selected when useful during implementation; running tests after every change is not required. Writing, restoring or running mid-tier tests requires a separate testing task explicitly requested by the owner. Do not write or restore low-tier tests.

[Complete inventory and tier justifications](docs/test-inventory.md) · [Machine-readable inventory](test-tiers.json)

Reviewed revision: `a80c617dd535d6e8142ce940ff73b7825f7e6c6c` (28 October 2026), plus the preceding local pruning changes. No tests were run for this reset.

## Selection and limits

6 active Python definitions and 0 active standalone programs; 1785 commented Python definitions. Also disabled: 0 named Node cases, 0 custom scenario functions and 2 standalone check programs. 1 broad entry points explicitly refuse. 26 low-tier cases remain removed from the prior review. These categories overlap in execution and must not be added into a runtime suite size.

Top-tier cases were individually read for the failure they observe. The remaining mid-tier labels are provisional execution decisions, not a claim that thousands of tests have passed a complete semantic review. Reassess value before restoring any of them. A browser program may contain many assertions; it is inventoried as one indivisible program, not as one asserted behavior.

## Active top tier

| Exact test selector | Why this case earns a place |
| --- | --- |
| [`test_recovery.RecoveryStoreTests.test_edit_during_final_audit_rolls_back_the_origin_claim_and_edge`](tests/test_recovery.py#L506) | Edits source during the final audit callback after a provider result exists. Requires transaction rollback of both the origin claim and its dependency edge, preventing publication against changed evidence. |
| [`test_recovery.RecoveryStoreTests.test_a_pair_in_error_keeps_the_step_reply_and_closes_its_activity_failed`](tests/test_recovery.py#L582) | Documented SYL-289 regression: a provider error previously closed activity as refused without an error and lost the recovery reply. Checks both the emitted partial-progress reply and persisted failed activity. |
| [`test_relation_occurrence_regressions.RelationOccurrenceRegressionStoreTests.test_mixed_closed_and_unclosed_same_ref_pins_valid_occurrence_and_reports_only_invalid_fault`](tests/test_relation_occurrence_regressions.py#L83) | Places valid and unclosed declarations of the same source in one document. Checks that occurrence-local validity creates one legitimate pin, reports only the malformed occurrence as faulty, and leaves reads non-mutating. |
| [`test_relation_selection_regressions.RelationSelectionRegressionStoreTests.test_same_literal_short_method_ref_cannot_redirect_existing_pin_to_unrelated_place`](tests/test_relation_selection_regressions.py#L202) | Replaces a previously pinned class with an unrelated class exposing the same short method name. Requires publication refusal and unchanged persisted relation state instead of silently redirecting the pin. |
| [`test_source_refs.SourceAddressTests.test_double_encoded_sequences_remain_literal_after_one_decode`](tests/test_source_refs.py#L92) | Uses double-encoded separators, traversal spelling and a name delimiter. Requires exactly one decode and a stable canonical address, protecting literal names from accidental reinterpretation. |
| [`test_store_acceptance.ProductStoreTests.test_exact_utf8_nul_bytes_projection_and_hash_guards_roundtrip`](tests/test_store_acceptance.py#L142) | Regression for quadratic dense-NUL projection: 100,000 NUL bytes must project within a finite SQL deadline. Also checks byte-preserving storage and independent database constraints on hashes and projections. |

## Running a selected top-tier case

Select the exact method, never a whole module as a substitute. Retain the original fixture prerequisites. A missing dependency, skipped case or unavailable database is not a pass. No live-provider check was promoted.

Use the existing runner with one exact `--select MODULE.CLASS.METHOD`. Store cases require `--store-settings /absolute/path/to/settings.toml` pointing at a server that permits disposable databases and the required extensions. The runner provisions the fixture; plain unittest cannot supply it.

```sh
PYTHONPATH=src python scripts/run_checks.py --select test_source_refs.SourceAddressTests.test_double_encoded_sequences_remain_literal_after_one_decode
```

## Restoring a mid-tier selection in an explicit testing task

1. Read the case and its helpers, reassess its information value, and identify the exact requested scope. Delete low-value cases instead of restoring them.
2. Uncomment only the selected `TEST-TIER-DISABLED-BEGIN` / `END` block by removing one leading `# ` (Python) or `// ` (JavaScript) from each original source line. Remove the marker lines. A bare `#` or `//` line inside a block represents an empty original line. Restore needed names from the complete `TEST-TIER-IMPORTS` statements at the file tail into their original scope and normal import section, rather than uncommenting them at the tail. Do not discard other local changes.
3. For standalone programs or custom scenario functions, remove only their adjacent `TEST-TIER-REFUSAL` stub or terminal refusal after restoring the actual implementation. Restore required shared helpers. The empty-suite `pass` is harmless and can be removed once a class has a real body.
4. Update both inventories to reflect the selection. Run only the requested scope, record actual results, then return mid-tier code to comments when the task finishes unless the owner asked to retain it active. Promotion to top tier needs a concrete, individually reviewed reason.

Broad build/qualification checks refuse while their implementation is commented. Preserve that refusal until the requested qualification has its necessary tests restored. A top-only run does not satisfy an old full-suite gate. Metadata verification, production validation, fixture helpers, Storybook examples and historical result records are not test passes and remain separate.
