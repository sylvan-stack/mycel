# Tests: mycel

Follow the [Test Strategy](/Users/msix/Artifacts/mycel/operations/test-strategy.md#when-testing-starts). Test work belongs to an eligible testing Beat or, outside a Saga, a separate testing task requested by the owner. Use test-free checks during implementation and keep low-tier examples commented at file ends.

[Mid-tier descriptions and justifications](MID_TIER.md) · [Complete inventory and tier justifications](docs/test-inventory.md) · [Machine-readable inventory](test-tiers.json)

Reviewed revision: `560e2e2b1623066240ebd128bfa1e552f0a4f25f` under SYL-327 (29 October 2026). No tests were run.

## Selection and limits

24 top-tier inventory entries and 135 mid-tier entries are available after the higher-bar review. 1653 low-tier entries were removed under SYL-327. Definitions, scenarios, programs and entry points overlap; this is not a runtime suite count. Retained mid-tier sources remain uncommented.

## Active top tier

| Exact selector or program | Why this case earns a place |
| --- | --- |
| [`test_top_cue_cards.CueCardTests.test_compile_keeps_exact_cross_root_targets_and_reports_faults`](tests/top/test_top_cue_cards.py#L68) | A real multi-root scan and published catalog show innermost ownership, fault isolation, and exact cross-file targets and source metadata. Review regressions check declaration and text boundaries at paragraph, empty list and nested list fences, written headings and anchor IDs with unequal backticks or a quoted HTML attribute, exact targets under ATX and Setext list headings, and whole-file trailing whitespace. |
| [`test_top_cue_cards.CueCardTests.test_fatal_compile_leaves_previous_catalog_bytes`](tests/top/test_top_cue_cards.py#L310) | An unusable artifact root and a failed atomic replacement both leave the prior catalog byte-for-byte usable and clean up staging files. |
| [`test_top_cue_cards.CueCardTests.test_match_uses_published_patterns_over_the_whole_message`](tests/top/test_top_cue_cards.py#L336) | The public matcher consumes the real catalog and distinguishes first appearance, fenced and multiline matches, plural suffixes, and false word-boundary matches. |
| [`test_top_cue_cards.CueCardTests.test_interrupted_hub_switch_resumes_and_preserves_first_backups`](tests/top/test_top_cue_cards.py#L378) | A real partial copy publication leaves durable pending state. Retrying and switching off restore agreement, preserve unrelated Codex bytes, and keep the first backups. |
| [`test_top_cue_cards.CueCardTests.test_heading_cards_preserve_prose_aliases_and_unique_anchors`](tests/top/test_top_cue_cards.py#L435) | The catalog preserves heading prose and aliases, disambiguates numbered anchors, and renders balanced inline links. Reference headings have the expected anchor, card ID and exact source text for valid or absent definitions, an ordered marker continuing a paragraph, and bracket text inside a URI autolink. |
| [`test_top_cue_cards.CueCardTests.test_invalid_escaped_scalars_report_faults_without_losing_valid_cards`](tests/top/test_top_cue_cards.py#L573) | Invalid escaped values and duplicate keys produce line-specific faults while a valid card still reaches the published catalog. |
| [`test_top_cue_cards.CueCardTests.test_directory_sync_failure_reports_the_published_catalog`](tests/top/test_top_cue_cards.py#L594) | A real atomic replacement followed by an injected directory sync failure leaves the new catalog in place and reports publication. |
| [`test_top_cue_cards.CueCardTests.test_malformed_tagged_values_leave_valid_cards_in_the_catalog`](tests/top/test_top_cue_cards.py#L619) | Malformed explicitly tagged scalar values become file-and-line faults while the real compiler publishes a valid neighboring card. |
| [`test_top_cue_cards.CueCardTests.test_html_container_declares_a_card_and_preserves_literal_examples`](tests/top/test_top_cue_cards.py#L640) | The published target removes a declaration after a multiline script end tag and retains cue lookalikes inside nested comments, verbatim HTML and fences. |
| [`test_top_cue_cards.CueCardTests.test_literal_nul_in_heading_preserves_catalog_publication`](tests/top/test_top_cue_cards.py#L671) | A heading with literal NUL bytes that resemble a renderer placeholder and a separate valid card both publish, with the affected card’s source heading and exact text preserved. |
| [`test_top_cue_cards.CueCardTests.test_malformed_front_matter_keeps_scanning_cue_files`](tests/top/test_top_cue_cards.py#L697) | Malformed tagged front matter leaves both the cue in that artifact and a cue in a separate artifact in the published catalog. |
| [`test_top_cue_cards.CueCardTests.test_html_tokens_preserve_cue_lookalikes_in_the_published_target`](tests/top/test_top_cue_cards.py#L727) | The published card distinguishes its declaration from cue lookalikes inside attributes spanning a blank line, inline comments, verbatim elements and fences. |
| [`test_top_ingest.IngestStepStoreTests.test_a_series_completes_while_a_file_changes_before_every_step`](tests/top/test_top_ingest.py#L8) | Documented SYL-315 regression of SYL-289 run 3: while another agent edited a file before every step, each step that wrote it started the refresh of unchanged files again, so a stepped pass never completed. Edits a file before every step of a series and requires the pass to complete within a bounded number of steps. |
| [`test_top_ingest.IngestStepStoreTests.test_a_refreshed_file_resting_on_a_written_file_is_refreshed_again`](tests/top/test_top_ingest.py#L29) | Non-obvious edge of the SYL-315 fix: a file the refresh already passed rests, through a Source Ref, on a section a later step writes. Requires that step to refresh it again, and the finished series to leave the dependency, edge, relation and stale rows exactly as one whole pass does. |
| [`test_top_recovery.RecoveryStoreTests.test_edit_during_final_audit_rolls_back_the_origin_claim_and_edge`](tests/top/test_top_recovery.py#L14) | Edits source during the final audit callback after a provider result exists. Requires transaction rollback of both the origin claim and its dependency edge, preventing publication against changed evidence. |
| [`test_top_recovery.RecoveryStoreTests.test_a_pair_in_error_keeps_the_step_reply_and_closes_its_activity_failed`](tests/top/test_top_recovery.py#L26) | Documented SYL-289 regression: a provider error previously closed activity as refused without an error and lost the recovery reply. Checks both the emitted partial-progress reply and persisted failed activity. |
| [`test_top_relation_occurrence_regressions.RelationOccurrenceRegressionStoreTests.test_mixed_closed_and_unclosed_same_ref_pins_valid_occurrence_and_reports_only_invalid_fault`](tests/top/test_top_relation_occurrence_regressions.py#L12) | Places valid and unclosed declarations of the same source in one document. Checks that occurrence-local validity creates one legitimate pin, reports only the malformed occurrence as faulty, and leaves reads non-mutating. |
| [`test_top_relation_selection_regressions.RelationSelectionRegressionStoreTests.test_same_literal_short_method_ref_cannot_redirect_existing_pin_to_unrelated_place`](tests/top/test_top_relation_selection_regressions.py#L11) | Replaces a previously pinned class with an unrelated class exposing the same short method name. Requires publication refusal and unchanged persisted relation state instead of silently redirecting the pin. |
| [`test_top_source_refs.SourceAddressTests.test_double_encoded_sequences_remain_literal_after_one_decode`](tests/top/test_top_source_refs.py#L11) | Uses double-encoded separators, traversal spelling and a name delimiter. Requires exactly one decode and a stable canonical address, protecting literal names from accidental reinterpretation. |
| [`test_top_store_acceptance.ProductStoreTests.test_exact_utf8_nul_bytes_projection_and_hash_guards_roundtrip`](tests/top/test_top_store_acceptance.py#L14) | Regression for quadratic dense-NUL projection: 100,000 NUL bytes must project within a finite SQL deadline. Also checks byte-preserving storage and independent database constraints on hashes and projections. |
| [`test_top_ids.IdentifierStoreTests.test_allocation_refuses_contention_and_lists_only_committed_issues`](tests/top/test_top_ids.py#L29) | Real advisory-lock contention and an uncommitted issue expose races in allocation and visibility. The next allocation reuses the rolled-back number and a separate connection verifies both purposes. |
| [`test_top_ids.IdentifierStoreTests.test_init_migrates_format_five_without_tying_issues_to_repository_lifetime`](tests/top/test_top_ids.py#L74) | A real format 5 store refuses allocation until init adds the table. The check verifies preserved generation and repository data, then removes the repository with the product's collection code and verifies the issue survives. |
| [`test_top_pieces.FilePiecesTests.test_working_and_head_match_ingest_across_rename_and_body_edit`](tests/top/test_top_pieces.py#L27) | A real Git index holds a third version, distinct from HEAD and the working file. Compares both reported sides with ingest and checks exact-byte digests and rename keys across a rename and a body edit. |
| [`test_top_pieces.FilePiecesTests.test_absent_and_unsafe_versions_are_distinct_without_mutation`](tests/top/test_top_pieces.py#L101) | An unborn and then deleted file exercise opposite version boundaries. An external symlink and invalid file bytes must be refused, with the checkout, Git metadata and external file preserved. |

## Layout and shared support

Case bodies are separated into [`tests/top/`](tests/top/) and [`tests/mid/`](tests/mid/). The former mixed test modules retain shared fixture classes, helper functions and imports at their established paths, with no inventoried test methods. This preserves existing subprocess paths, patch targets and fixture imports without copying helpers into both tiers. Compatibility entries preserve original package and resource paths while loading the mid-tier implementation. Product-side test APIs load it only when invoked and refuse if the test source is absent.

## Running a selected top-tier case

Select an exact method when it resolves a concrete uncertainty; no run is required after an edit. The new module names begin with test_top_ so they cannot shadow the shared fixture modules. Do not run whole folders or discovery as a substitute. Original prerequisites, skips and environment limitations still apply. A focused result is not full qualification.

The fixture-aware runner defaults to tests/top and also imports shared support from tests. Store cases still require an explicit disposable-store settings file.

```sh
PYTHONPATH=src python scripts/run_checks.py --select test_top_source_refs.SourceAddressTests.test_double_encoded_sequences_remain_literal_after_one_decode
```

## Mid-tier execution

[MID_TIER.md](MID_TIER.md) lists the descriptions, tier reasons and review status. The retained source stays uncommented. Mid-tier work belongs to a testing Beat or separate testing task, with explicit owner scope for execution. Inspect prerequisites and indirect calls before invoking a program or qualification entry point. A focused result is not full qualification.

For a Python method, use the same fixture setup as the top tier, put the mid folder on PYTHONPATH, and select `test_mid_<module>.Class.test_method`. Mycel's fixture-aware runner accepts `--tests tests/mid --select test_mid_<module>.Class.test_method`; store cases require explicit disposable-store settings. Archived scenarios and programs retain their original compatibility entry paths.

Restoration under SYL-326 used static checks only. No tests, Builds, provider calls, Origin migrations or corpus ingest were performed. Original prerequisites and environment limits still apply.

## Qualification after SYL-327

The source runner continues to require exact selections. Reduced selections are not historical full qualification: `tests/qualification-status.json` records that a separately requested qualification task must review the requirement mapping before a complete run can write the named checks again. No tests, Builds, provider calls or owner-store operations ran during this pruning.

The review used an AST census of calls, assertions and patch boundaries, followed by targeted inspection of retained case bodies and fixtures. This is risk-based retention, not a runtime proof that the removed coverage is redundant.

## Builds

Since SYL-329 (29 October 2026) a Build runs the top tier only (MYC-D73). Its automatic gate selects every `unit` and `store` check under `tests/top/` and no mid-tier check, and refuses when `tests/top/` has no test source or a top-tier source is commented. The mid tier runs only when the owner asks for a mid-tier run. A passing top-only Build is not full qualification and does not rewrite the named checks.

## Separate testing and archived examples

All test work is separate from implementation, including top-tier regressions,
fixtures, snapshots, classification, archival maintenance and runner changes.
Use the testing Beat's documented scope or the scope of the owner's separate
request. A test-running Build keeps its full top-tier gate. A test review,
writing or archival task does not itself authorize execution.

Read the retained cases and the `LOW TIER — DO NOT ENABLE OR RECREATE` footers
before adding related tests. They preserve rejected historical source, reasons
and revisions, so obvious or redundant checks are not generated again. All
archived lines are comments, including imports and registrations. They add no
runnable coverage. Re-admission requires distinct new evidence and testing
scope that covers the change.
