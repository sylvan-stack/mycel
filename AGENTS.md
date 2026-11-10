# Repository instructions

## Test execution policy

Follow [TESTS.md](TESTS.md), [MID_TIER.md](MID_TIER.md), the linked inventory and
the owner's [Test Strategy](/Users/msix/Artifacts/mycel/operations/test-strategy.md).
**Test work belongs to the Arc's testing Beat or a separate testing task.**
Testing Beats start under normal Beat eligibility. Outside a Saga, the owner
explicitly requests the testing task. Use test-free checks during implementation.
Do not add, edit, fix, refactor, classify, retire, restore or run tests, fixtures,
snapshots, runners or inventories as part of implementation. Existing tests may
be read as source reference. Record relevant test impact for the testing Beat
or separate task.

Keep runnable suites small. A new function, branch or option does not need a
matching test automatically. Each retained case must add distinct consequential
information. Routine permutations, copied defaults, mocked success/forwarding
and redundant CRUD are low tier; use the strategy's examples and admission bar.
Before adding a test in an authorized task, read the nearby retained cases and
low-tier comments so the rejected idea is not recreated.

Keep existing rejected cases as literal comments at the end of their test files,
marked `LOW TIER — DO NOT ENABLE OR RECREATE`, with original ID, reason, retained
evidence when applicable and source revision. An entirely low-tier file is
comment-only. Record low/commented status and footer location in the inventory.
Never use skipped tests, disabled suites or executable wrappers as archives.
Re-admission requires new evidence and testing scope that covers it.

Keep retained top/mid source in the repository's documented layout and state.
A testing Beat or separate task that calls for a Build runs the whole top tier
through the Build gate. Mid-tier execution additionally requires the owner's
request for that scope. Do not
bypass a gate or call a reduced selection full qualification. Test-free static
syntax, type and compilation checks remain available. Report checks not run.
This policy supersedes older automatic testing and top-tier exceptions.
