# Requirement checks

The packaged registry in `src/mycel/data/requirements.json` contains all 332 active requirements from the accepted MYC-0 through MYC-16 Requirements tables. It preserves each requirement's text, origin, check kind and source specification, plus the SHA-256 of each source chapter. MYC-9.10 remains active: its `Dropped` origin requires Mycel not to present code results as documented in the overview.

Specification acceptance authorizes implementation. It does not establish runtime acceptance, provider qualification or a distributable working Build. The registry records accepted specifications; `checks/claims.json` separately names the requirements this implementation claims and the exact checks that prove each one.

Run the staged automatic gate from this repository with its prepared environment:

```sh
make check
```

The command uses `.venv/bin/python`, discovers every test and runs all declared
`unit` and `store` checks. Its terminal summary reports outcomes, check kinds,
proven and pending requirements, elapsed time and named failures. Six workers
run by default; `WORKERS=1` selects serial execution. Parallel runs use separate
spawned processes so a unit check's network denial and a store check's private
`MYCEL_CONFIG` cannot affect a concurrently executing check in another worker.
Each worker executes one method at a time.

Select a module, class or method for development, or combine selections in one
space-separated value:

```sh
make check TESTS=test_store_gate
make check TESTS=test_store_gate.StoreGateTests
make check TESTS="test_store_gate.StoreGateTests.test_real_store_proofs_are_private_executed_and_discarded test_check_store"
make check WORKERS=6 STORE_SETTINGS=/path/to/config.toml REPORT=/path/outside/repo/report.json
```

Selectors retain canonical test IDs and reject unknown selections. A focused
run executes only those methods and retains a claim only when its entire proof
list is selected. A passing focused run supplies development evidence; full
requirement acceptance requires the complete `make check` run and any separate
installed or live qualification required by the task.

`REPORT` writes the complete JSON report; keep it outside the repository. The
compatible coverage command uses the same runner and emits the original complete
JSON report on standard output. Its `--select` option can be repeated:

```sh
.venv/bin/python scripts/check_coverage.py --store-settings ~/.mycel/config.toml --workers 6
.venv/bin/python scripts/check_coverage.py --store-settings ~/.mycel/config.toml --select test_store_gate --select test_check_store
```

Every check must name its requirements using `@proves("MYC-0.1", ...)`; the optional `kind` is `unit`, `store`, `eval` or `live`. A claim needs at least one named check that declares that requirement, has its required kind, executes in this run and passes. Missing declarations, duplicate check names, unknown requirements, wrong kinds, skipped checks, expected failures and ordinary failures reject the gate. A passing unrelated test does not qualify a claim.

<!-- sources:
mycel:@code/Makefile
mycel:@code/scripts/run_checks.py#main
mycel:@code/scripts/check_coverage.py
mycel:@code/src/mycel/_coverage.py#select_checks
mycel:@code/src/mycel/_coverage.py#run_checks
mycel:@code/src/mycel/_coverage.py#_parallel_checks
-->

The staged gate permits unclaimed requirements to remain pending. Its report lists all active requirements, their accepted specification status, runtime status and passing proof names. The current private prepared claims name 315 requirements with unit or configured real-store
proofs. Scoped scan/identity acceptance includes trusted persisted parse reuse,
dual-root document origin, checked moves and exact located versions with their
own retained pins/evidence. MYC-D37 reconciles the prescribed named shared selections and scan
exclusions, and MYC-D38 permits the separate parsed declaration-name identity
key. The remaining requirements stay pending. Passing an internal prepared slice
does not complete its task while other owned requirements or native prerequisites
remain open. Activity store checks exercise injected transaction callers and
actual retained-reference pass writes, including cross-repository changes,
cumulative reply counts, no-ops and failure rollback. Numbered packaged
initialization and disk file/identity producers now use the activity substrate.
The scoped public embedding command has named store proofs for scope,
resume/retry, read-only dry-run and coverage reporting, including current
eligibility and acknowledged progress after connection loss or interruption.
Dependency acceptance covers exact version pins, independent ownership,
current direct reasons and retained dependency/relation lifecycle through guarded
producer APIs. Mechanical propagation now has named unit/store proofs for
complete same-pass publication, direct and indirect reasons, exemptions,
scoped pending/retry, exact version pins and audit/physical-input rollback.
Public confirmation proofs cover exact current-version guards, atomic
pin/evidence/activity rollback, source-free defaults, invalid refs and deleted
source withdrawal. Verification history proofs cover exact applicability,
selection membership, branch/version switching, independent record ownership,
unlocated-version collection, logical deletion and explicit strict migration.
Listing is deterministic and read-only, including successful empty scope.
Retrieval candidate checks exercise current disk selection, disabled and shared
scope, full body/name/path BM25 access with incomplete embeddings, complete
current-model cosine plans and logical-chunk collapse before candidate limits.
Organization members retain separate candidate replies and per-member counts.
Recursive freshness checks cover explicit declared/asserted upstream closure,
valid missing refs, newly captured declarations, code-only governance, selected
shared suppliers and downstream updates without extra result or scan scope.
Deadline proofs exercise nested Git/child work, bounded SQL, late-publication
rollback and committed-index fallback, including activity setup or close faults.
No-fresh proofs retain every store row exactly. Changed upstreams retain
unchanged dependant text, pins, vectors and unrelated repository rows.
The reusable mutation/liveness API now has named proofs for all ten owned
MYC-12 requirements, including exact final replies, atomic final-close retry,
classification detail rollback and read-only unfinished status. Real command
producers connect their feature writes and final replies in their owning tasks;
public activity history now lists ordered summaries and exact entry details.
Retention proofs cover independent repository/global limits, exact live
invocations, concurrent and stale-snapshot writers, atomic pruning rollback and
preservation of independent evidence. Offline Build staging checks verify
packaging, complete retained metadata and terminal registry immutability;
complete installed-release qualification remains a separate gate.

Retrieval evaluation checks use the ordinary candidate and ranking producers
inside one shared read-only index snapshot, with query preparation beforehand.
They cover ten-result parity, routes, scopes, citation bridges, shared aliases,
concurrent publication, fallback and explicit selected-kind dispatch. Controlled
query vectors prove integration without supplying a real ranking measurement.
MYC-4.25 evaluation and the separate Drift pipeline remain pending. A prepared
claim becomes accepted only after its named checks pass the complete gate.

The fourteen MYC-10 claims are prepared for the next complete validation.
Twelve new unit methods and two configured real-store methods cover literal
PATH-selected grep arguments/streams/status, conservative option and pattern
selection, repository scope, the marked five-result normal-search tail,
query-independent formatting and unchanged store rows/sequences. Optional
search/render/write/flush/interruption faults preserve the completed grep
status. The focused diagnostics passed after the recorded path-alias fixture
correction and unexpected-tail-exit containment; their earlier failed report
remains retained. This inherited grep preparation supplies 1,502 methods
(893 unit/609 store) and 310 ordered claim lists before the launcher additions.
It is not runtime acceptance: its own fresh complete development/installed pair
and independent review must pass after the 1,488-method predecessor is accepted.

Five additional launcher claims are prepared privately for MYC-0.9 and
MYC-15.6, MYC-15.7, MYC-15.9 and MYC-15.10. Twenty new unit methods exercise
numeric intact Build selection, actual process arguments/cwd/PID/streams/signals
and grep status, independent installation, nonblocking selection/prune locks,
withdrawal and partial prune/install outcomes. One configured real-store method
checks installation/selection and compatible version rollback while settings,
all store rows, schema and sequences remain unchanged. Actual focused diagnostics
passed all 21 new methods; the earlier failures and their narrow fixture/product
repairs remain retained. Synthetic runtime/bundle fixtures are protocol and
process proofs, not pinned release qualification.

This private preparation with the conditional summary correctness carry has
**1,524 methods (913 unit/611 store), 315 named claims and 17 pending requirements**. All inherited 1,502 declaration metadata
rows and 310 ordered claim lists remain exact. No launcher claim is accepted:
SYL-136 remains Backlog until an actual accepted SYL-135 handoff and native Done
state permit integration, its own fresh complete development/installed pair and
independent review. Working publication and full release qualification remain open.

The summary correctness carry retains every prior 1,523 declaration and all315
ordered proof lists. It changes only the two public summary publication callers
and adds one standalone configured-store regression. Final build, regeneration
and memberless-deletion publication acquire only the nonblocking affected owner
closure; busy owners refuse the current publication, services run without pass
locks, and earlier acknowledged regeneration results remain truthful. The new
proof covers actual busy downstream refusal, retry, disjoint busy-repository
independence and service-time lock availability. The source repair has an authentic earlier 11 PASS/1 fixture FAIL run and a
separate corrected-fixture sole-store PASS, each with independent result review.
These are separate runs, not a fresh twelve-method PASS. The carry requires
exact evidence reconciliation and independent/root review first. It registers no
new claim and does not inherit the unrelated 144–149 provider/replacement branches.
The resulting launcher candidate still requires its own fresh complete pair.

<!-- sources:
mycel:@code/src/mycel/_summary_build.py
mycel:@code/src/mycel/_summary_regenerate.py
mycel:@code/tests/test_summary_publication_guards.py
-->

<!-- sources:
mycel:@code/checks/claims.json
mycel:@code/tests/test_activity_history.py
mycel:@code/tests/test_activity_retention.py
mycel:@code/tests/test_packaging_contract.py
mycel:@code/tests/test_evaluation_retrieval.py
mycel:@code/tests/test_evaluation_store.py
mycel:@code/tests/test_grep_tail.py
mycel:@code/tests/test_grep_tail_store.py
mycel:@code/src/mycel/_grep.py
mycel:@code/tests/test_launcher_selection.py
mycel:@code/tests/test_launcher_installation.py
mycel:@code/tests/test_launcher_maintenance.py
mycel:@code/tests/test_launcher_store.py
mycel:@code/src/mycel_build/_launcher_runtime.py
mycel:@code/src/mycel_build/_launcher.py
mycel:@code/src/mycel_build/_maintenance.py
-->

Summary plan/report proofs cover current document eligibility, complete current-model coverage and disjoint membership counts, read-only snapshot/lease refusal, exact bounded leaf request estimates, stored missing/stale membership, full regeneration plans and single-repository command scope. Grouping unit proofs execute pinned PCA/Gaussian mixtures and check canonical numbering, BIC/probability ties, multipart means, singleton promotion, request splitting and both stop conditions. Generated provenance store proofs cover exact successful request/response
publication, retained independent ownership, refusal/cancellation/corruption
rollback, compatible state/member pins, same-transaction lower/higher output
composition and mechanical regeneration work with no semantic Drift or calls.
Public build store proofs now cover private lower/higher levels, real response
vectors, complete tree replacement, exact source/settings checks, empty-set
metadata, failure/cancellation rollback, invocation leases, concurrent ingest
and summary/removal lock contention. Actual published summaries exercise
multipart maximum cosine, mixed document margins and limits, foreign shared
exclusion, stale annotations, generated-target faults and no code bridges.
Regeneration proofs cover lowest-first fixed membership and places, missing
member deletion, failed-child blocking with independent success, exact physical
input and final audit rollback, multipart/cut responses and interruption with
acknowledged progress. Removal proofs cover atomic set/metadata/vector/pin
withdrawal, typed metadata refusal, independent evidence retention, empty
no-ops, lock contention and committed counts after final audit/close faults.

Overview checks cover complete stored disk outlines, empty and unnamed files,
ordering, duplicate and nested classes, both eight-symbol caps and exact omitted
counts. Configured-store proofs check atomic final publication and actual late
input-guard rollback, quiet rebuilds, directory removal, body-only vector
preservation, normal embedding, fresh-search reconciliation, document margin
and limits, code-only/shared exclusion, no edges or code bridges, stored read
and report behavior, and exclusion from summary membership. Unit report checks
reject escaping directories before store access and accept empty stored scope
without source folders or freshness/model work.

Exact-pair Drift checks exercise local work projection, categorical stage
results, retained Jev/review evidence, changed-input history and selective
reason closure. They distinguish source removal, failed reads and inactive
versions and preserve stale marks, pins and verification records across every
classification result. Heartwood and generated policies retain their existing
exceptions. Model adapters and canonical request assembly keep their separate
requirements.

Canonical classification store proofs cover all seven owned evidence/guard
requirements: complete pinned/current/dependant/governor/ancestor bytes and
ordered family/file membership; retained exact canonical request and bundle
bytes; independent related inputs; initial/future/preserved full-file clocks,
tombstones and removed selections inside live files; command/revision/settings
identity; missing/corrupt/ownerless evidence refusal; unchanged later cache
reuse; obsolete application and final-publication rollback; and invocation
leases without pass locks during adapter I/O. Provider execution and public
finite command acceptance retain their downstream owners.

Protocol-1 reviewer unit proofs exercise literal frozen commands and the exact
private environment, closed unrelated descriptors, complete LF/EOF requests,
concurrent bounded pipes and strict success/failure identities, citations, usage
and exit combinations. Hanging/overflowing/cancelled process and descendant
fixtures check termination, reaping and private-directory removal before a
parent retry. Complete public setup fixtures recompute governor/ancestor text
bytes, hashes, locators and wire budgets. The adapter launches once, returns
only validated judgements or safe typed faults, and performs no provider retry.
Finite classification proofs now exercise deterministic pair order/caps, two
concurrent protected attempts, no pass lock during calls, nonblocking contention,
exact dry-run bytes/readiness and complete store immutability, retries and safe
terminal errors, deadline/interruption cleanup, obsolete policy inputs and
same-transaction classification activity rollback. Local unit proofs verify the
original search/read allowance, no provider/credential/child boundary and guarded
cache effects without repeating current completed judgements. Read-only report
store proofs cover complete stale direct/removed/upstream paths, generated
regeneration work, separate current/closed/inactive stages and exact reference
counts, while every table row and sequence remains unchanged. Live qualification
remains separate work.

Diagnostic and repository-removal proofs cover complete disk/branch/stash identity counts,
last-pass timestamps, current-model version and part coverage, ineligible/deferred
counts and concurrent read-only snapshots. Known disabled, orphan and empty
repositories remain inspectable without source folders, and ordinary work excludes
ineligible names. Removal checks cover exact owned-row counts, complete rollback,
nonblocking live-operation/lease refusal, receipt cleanup, global numbered activity,
retained foreign baselines, protected history and atomic repin/collection. Common
repository refusals preserve every member, including all-refused scopes and
interruption after a committed removal. Info preserves settings/store faults without
model credentials or writes.

Closed-history store proofs cover deterministic 1,001-bundle pruning, protected
current/open/baseline/verification/request evidence, exact repeated-input
archiving, late obsolete stage results, atomic metadata/owner/blob rollback,
read-only reports and independent activity deletion. Guarded removal checks
refuse live mutations and preserve foreign dependant-owned copies. Rebuild
proofs compare new-generation CLI initialization/ingest with exact binary store
restoration, including original pins, verification and canonical classifier bytes.
Activity details expose their stored index-generation identity.

Direct document-link proofs cover both directions and dependency kinds, whole
files and class families, current anchored versions, more than two unembedded
sections and root collisions. Relations, generated, transitive, disabled and
branch-only endpoints remain excluded. Search flags are query-independent;
read lists are complete. Undocumented-code proofs cover deterministic root/path/
name ordering, repeated component-boundary filters, deletion of the final link,
actual new/removed Source Refs across fresh/no-fresh runs, and exact report
immutability without creating assertions or querying a model.

Exact read proofs cover code, checkout/artifact documents and index-only
summaries/overview sections, exact retained bytes including NUL, class headers,
short methods/titles, qualified/legacy addresses, overlapping aliases and root
or namespace collisions, including newly captured collisions during a fresh
read. Reply proofs preserve stale paths, Heartwood,
dependency faults and incomplete-check metadata, optional bounded file context,
escaped-symlink refusal and UTF-8 text truncation. Real-store proofs exercise
recursive source checking, changed/new exact text, no-fresh row preservation,
expired-budget fallback, concurrent busy upstreams and disk-only declaration
faults for text versions shared with a branch. A real Git restoration proof
keeps branch-only text ineligible and checks restored text by its original
identifier, including its recursive declared sources. Generated summary reads check
exact generated members and their transitive source repositories without
regenerating text, renewing pins or invoking providers. The command guide
contract and info commands/readReply are checked with the same staged gate.

Search proofs compare identical result/citation dependency annotations,
original stale sources and intermediate paths, exact current-version check
completion, canonical root/address collisions and stable IDs. Offline bounded
query stand-ins exercise missing credentials, local complete-query limits,
provider failures, invalid/zero vectors, cancellation and dimension mismatch
without query provider access. Disposable store
checks cover partial/failed/current-model plan counts, selected shared
documents, separate organization replies, recursive stale propagation,
ref-fault isolation, exact pending captured section/heading attribution,
unverifiable tokenizer coverage, and busy/no-fresh/expired-check index fallback. Search
performs no pending corpus embedding or semantic classification.

The automatic gate discovers mandatory real PostgreSQL foundation,
repository-fixture, product-schema, concurrency, evidence, embedding and activity
checks. `make check` selects the configured dedicated local server from
`~/.mycel/config.toml`; `STORE_SETTINGS` overrides that path. Each store method
gets a new generated database; the owner's
actual database is never opened. The complete staged gate can now pass;
full contract/release acceptance still fails until all 332 requirements have
passing proofs, packaged-runtime checks and explicit required live qualification.
A run without a backend still fails its mandatory store checks.

A task acceptance record may summarize its own executed proofs. Settings, private credential access and offline embedding plans have passing proofs for their owned unit requirements, and the configured automatic store checks now execute against the delegated local server. Task completion does not qualify a working Build, clear another requirement, or remove a native prerequisite. A separate public-dummy Keychain probe verifies the system reader without reading owner credentials; automatic unit checks use bounded child stand-ins.

Verify the source snapshots explicitly when the authoritative specifications are available:

```sh
.venv/bin/python scripts/check_coverage.py --store-settings ~/.mycel/config.toml --specifications /path/to/mycel/specs
```

The packaged registry remains usable without that artifact checkout. Snapshot verification rejects a source chapter whose contents changed after extraction. Reconcile the registry and its checks with any accepted specification change before claiming the affected behavior.

The stricter full contract gate additionally rejects every pending requirement:

```sh
make check-release
```

This gate intentionally fails while the implementation is incomplete. Passing the staged gate is not full contract acceptance or packaged-runtime qualification. The release check still executes only unit and store checks; it never starts evaluation or paid calls. It rejects focused selectors because full contract acceptance requires the complete inventory.

Evaluation and live checks remain explicitly requested work. The internal `run_on_demand_checks` helper records their executed results with the immutable implementation identity and registry fingerprint. A release tool can give those records to `run_checks` for the same identity; stale records, failed checks and mismatched requirements cannot qualify a claim. The current command-line gate does not load external acceptance records or invoke that helper.

Unit checks reject Python socket and native PostgreSQL connection paths. Build checks use deterministic stand-ins rather than embedding, Jev or reviewer providers; provider qualification remains separate work. The test helper's simulated acceptance examples exercise gate behavior and make no service calls.

Disposable Git fixtures use Git's existing configured identity and hooks. They
set no author, committer, date or identity configuration and disable no hook.
Missing configured identity or a rejected fixture commit fails the check;
fixtures never invent an identity or bypass the commit guard. Product Git
reads preserve configured hooks while refusing mutations and disabling
optional index writes, configured executable readers and lazy fetching.

A store check requires a real disposable database backend. `disposable_store` chooses a unique `mycel_check_` database for each check, validates its address before calling the backend, writes a private settings file, sets `MYCEL_CONFIG`, initializes the database, and removes it and the settings directory afterward. It attempts database removal after initialization or check failures; a cleanup failure fails the check. Simulated backends never establish actual store acceptance.

Native cleanup uses ordinary `DROP DATABASE` only for a database whose creation
this backend acknowledged. PostgreSQL holds the database lock while waiting up
to five seconds for other backends to leave, within the fixture's finite statement
timeout. This allows short-lived extension workers to finish without requesting
permission to terminate a different role. Persistent connections still fail
cleanup; a matching name prefix never grants ownership of an existing database.

The runner records each acknowledged native creation atomically in a private
directory for that run. Successful removal deletes its record. After workers
exit, the parent recovers any remaining recorded databases, including after
cancellation or a worker crash. Recovery requires an exact valid record bound to
the configured server, rejects the owner's database, and keeps failed removal
records in their private directory after a failed run, reports that path, and
leaves them available for a safe retry. It never removes a database merely
because its name has the generated prefix. A creation that fails without
acknowledgement grants no cleanup permission.

<!-- sources:
mycel:@code/src/mycel/_check_store.py#NativePostgresBackend
mycel:@code/scripts/run_checks.py#main
-->

The internal `initialize_store(backend, settings_file)` test hook supplies a per-check initialization callback. Without that hook, the backend runs the actual in-process `mycel init` command with its private config. The foundation's `test_store_gate.StoreGateTests.test_real_store_proofs_are_private_executed_and_discarded` retains a small SQL probe table to test the gate itself. It checks real database/config identity, insert/read, refusal of unsafe database names before connecting, cleanup after success, assertion failure, cancellation and failed initialization, and rejection of uncovered proofs and cleanup failures. Product-schema, dimension/migration and concurrent-lock acceptance checks use their own real generated stores. An explicit empty-store callback lets the store task test init itself. Callbacks are test code, with no product setting or option; a successful probe alone does not qualify another feature.

Override the configured PostgreSQL server for either command:

```sh
make check STORE_SETTINGS=/path/to/config.toml
.venv/bin/python scripts/check_coverage.py --store-settings /path/to/config.toml
```

The runner reads only `store.address`, discards the owner's database name for connections, and administers the generated database through `postgres` or `template1`. It never connects to the owner's database, even when that name itself begins `mycel_check_`. It accepts a password-free PostgreSQL URI with only `sslmode` and `connect_timeout` query options. The default backend uses the product's native connection inside each test worker and private challenge-only Keychain reader; it needs no `psql` executable. A reachable owner-configured server with database creation permission is still required.

Before dispatching selected store checks, preflight actually connects, creates
and removes one disposable database through the same journal. Failure produces
a short server diagnostic containing only a safe `host:port` label and the
connection/creation fault, without authentication or provider bodies. Unit checks
can still execute; store checks fail without repeating the unavailable connection.
Real-store acceptance requires named passing methods against that configured
server and registration in the claims report; the current source-bound checkpoint
provides those proofs for completed foundation/store tasks. An exploratory SQL
probe against an independently selected server is development evidence and does
not satisfy the owner-configured-server contract.

For focused unit development, a test file can also run with the standard Python test runner:

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_coverage.py -v
```

Plain `unittest` discovery retains the same canonical test IDs but supplies no
store fixture. Store checks run through `make check` or the compatible coverage
command to receive their private database. The complete automatic gate remains
the acceptance check because it enforces declaration, execution and claim rules
in addition to ordinary test assertions. Focused runs never replace it.

Installed automatic checks use the sealed pinned interpreter and installed
product modules. Their ordinary generated-store fixture initializes only the
schema through the installed private store implementation; explicit init
fixtures retain empty databases and run the actual numbered CLI initialization,
including its transaction-bound activity. This keeps unrelated feature tests
independent of bootstrap audit rows without suppressing installed-init proofs.
Temporary development-identity and mocked SQL tests explicitly select their
development seams; installed identity, isolation and real initialization tests
continue to exercise the numbered package.

For a numbered Build, the parent derives the automatic method inventory, registry
and ordered proof claims from frozen source without importing the tests. The
installed runner must discover that same complete inventory and return every
named unit/store outcome plus the exact reconstructed 332-row requirement map.
Omitted, substituted or extra methods, changed requirement order/kinds, forged
provider acceptance, or missing named proofs refuse qualification. Records never
turn a pending eval/live requirement into an automatic pass.

The packaged gate also exercises real selector and CLI execution at two private
paths with source/developer access, downloads and writes denied. It checks CWD,
explicit/default/withdrawn selection, JSON/grep streams and cancellation. Passing
unit fixtures for its protocol or process mechanics is not a native packaged
result. A working publication still needs the complete genuine Build results;
this gate neither publishes nor installs a working Build for the owner.

The separate full SYL-135 candidate1 gate remains rejected (1,501/1,502 named
checks passed in each environment). The accepted checkpoint remains the earlier
1,488-method/296-proof pair; this future launcher preparation and summary carry
do not qualify that failed candidate or authorize any native closure.


## Selective SYL-146 preparation on the current automatic source

This isolated continuation preserves every 1,562 prior automatic declaration
and all 315 ordered shared claim lists, including the latest 144 non-live public
status/service-denial tests and 145 protected process/packaged-check fixes.
Eight additional service-free unit methods give 1,570 automatic methods
(958 unit/612 store), 399 source inputs and 267 check inputs. The 332-row
registry is unchanged. No live/eval claim or measured provider result is added;
all old donor focused results remain historical rather than new validation.

## Prepared explicit provider operations

The private SYL-146 path uses the production canonical fixture runner and actual
configured Jev/reviewer only on explicitly selected live Drift evaluation. A pure
qualifier checks distinct200/critical50/unchanged50 floors including all four
critical categories, zero suppressed
critical work, stable identity and comparative reviewer improvement on a common
routed subset. Aggregate and category diagnostics expose meaningful misses,
unnecessary work, support precision and escalation with explicit denominators
and null empty shares. Automatic stand-in checks exercise these boundaries but cannot
qualify a provider. The fixed embedding compatibility helper likewise requires
explicit live choice; exact submitted tokens, conservative planning tokens and
reported input usage remain separate. No real provider operation or owned
MYC-13.9/MYC-13.19/MYC-13.20 proof is claimed by this preparation.

<!-- sources:
mycel:@code/src/mycel/_evaluation_live.py
mycel:@code/src/mycel/_provider_qualification.py
mycel:@code/src/mycel/_embedding_live.py
mycel:@code/src/mycel/_provider_checks.py
mycel:@code/tests/test_provider_evaluation.py
-->


## Selective SYL-147 conformance and report consumer preparation

This isolated continuation preserves all1,570 prior automatic method bodies,
decorators and ordered declarations, the315 ordered shared claim lists and
complete332-row registry. Three retained provider-report unit methods, four
new same-process caller boundary unit methods and one genuine public-CLI store
conformance method give1,578 methods (965 unit/613 store),402 source inputs and
270 check inputs. These are static inventories; no new check has run here.

The real-store conformance fixture covers stored Drifts, the quiet-period/Jev/
review route without a change-size threshold, relations without authority,
recorded verification, and generated publication/regeneration. It checks
retained deletion evidence and that still-supported closure preserves pins and
mechanical staleness. Its final clock repair is retained. The current parent
already has the exact summary publication guard and confirm-empty regression
bytes, so no duplicate repair or test is copied.

The pure provider consumer retains full quality/provenance/usage/time/cost
fields and rejects changed or incomplete reports. The explicit same-process
group caller executes146 once and passes its original proof/reports objects to
this147 consumer, which executes only the named14.22live check and returns
separate proof objects without extra provider dispatch or JSON proof loading.
The trusted caller and its code/result review establish object provenance;
public dataclass fields and a plain dictionary do not authenticate origin. Unit fixtures patch provider operations with fictional reports;
their ephemeral live-executor records test local boundaries only and establish
no real provider qualification. No2.23store or14.22live claim is registered.
No148working publication or149replacement behavior is carried forward.

<!-- sources:
mycel:@code/src/mycel/_provider_deployment.py
mycel:@code/tests/test_provider_deployment.py
mycel:@code/tests/test_provenance_conformance.py
-->

## Selective148 publication-policy preparation

Seven additional unit declarations preserve every1578 prior method body,
decorator and ordered requirement list, giving1585 automatic methods
(972unit/613store),406 source inputs and274 check inputs in this isolated copy.
The315 ordered shared claims and332-row registry are unchanged. These are static
inventory facts, not new runtime proofs. Publication fixtures construct openly
fictional complete327-automatic requirement preconditions and real disposable
files/locks/replacement boundaries. Positive protocol flags are not actual
native or Keychain evidence. That original preparation retained an unsupported
private credential placeholder. The later public-fixture integration below
replaces it; any missing automatic requirement still blocks working qualification.
No old focused result is promoted to this snapshot.

<!-- sources:
mycel:@code/tests/test_working_publication.py#publication_contract_inputs
mycel:@code/tests/test_working_publication.py#WorkingPublicationTests
mycel:@code/src/mycel_build/_publication.py#publish
-->

## Selective149 read-only replacement preparation

Eight new unit methods preserve every1585 prior whole method and ordered
declaration, giving1593 automatic methods (980unit/613store),409 source inputs
and276 check inputs. The315 shared claim lists and332-row registry remain exact.
The new rehearsals use real disposable filesystem effects and an explicitly
finite catalog executor. They check exact ownership/bindings/ordered steps,
uncertainty, restrictive SQL text, preserved shell remainder/source/unrelated
objects, and early/late partial outcomes. They are not real PostgreSQL execution,
an owner replacement or native release qualification. No new test has run here;
all old source-specific results remain historical rather than new validation.

<!-- sources:
mycel:@code/tests/test_replacement.py#ReplacementTests
mycel:@code/src/mycel_build/_replacement.py#replacement_plan
mycel:@code/src/mycel_build/_replacement.py#validate_replacement_report
-->

## Private public-fixture credential check

The automatic publication path now has a current-Build private credential
producer and one pure strict receiver shared by qualification and publication.
It binds the actual target, Build number, source/check identities, full readonly
program manifest, current helper hashes and licensed public fixture provenance.
The actual installed reader consumes the explicit private command output only
in memory. Client network denial, private native-handle scope, cleanup and
profile-view preference equality are recorded with their real limits; no global
owner-state, daemon-isolation, default-login or newly created native-item claim
is substituted. A failed or unavailable native check remains a named failed
group and preserves the previous working selection.

Fifteen new unit declarations cover fake-native explicit-handle/cleanup faults,
closed producer/receiver identities, honest scoped preferences, offline fixture
provenance and unknown nested launches. They use stand-ins rather than real
Keychain or provider operations. A source-only declaration is not a passing
proof; the source and full named inventory must be recaptured and genuinely run.
The five on-demand evaluation/live requirements remain separate from automatic
Build qualification and do not require another paid measurement for this check.

<!-- sources:
mycel:@code/src/mycel_build/_keychain_probe.py#probe_private_keychain
mycel:@code/src/mycel_build/_credential_contract.py#credential_probe_passed
mycel:@code/tests/test_private_credential_reader.py#PrivateCredentialReaderTests
mycel:@code/tests/test_private_credential_contract.py#PrivateCredentialContractTests
-->

## Final automatic Build preparation — 16 October 2026

This separate candidate carries **327 proposed automatic proof lists** while
retaining all315 existing ordered lists. Its complete automatic inventory is
**1,608 methods (995unit/613store)**; the five evaluation/live requirements stay
outside the automatic claims. The proposed mapping is not passing evidence.
This final source has not completed either full development/installed gate or
its own Build's native, private-credential and packaged qualification checks.
Focused diagnostics do not qualify this Build or publish a working selection.
Actual full-Build results and independent review remain pending.

<!-- sources:
mycel:@code/checks/claims.json
mycel:@code/src/mycel_build/_automatic.py#automatic_contract
mycel:@code/src/mycel_build/_qualification.py#qualification_certificate
-->
