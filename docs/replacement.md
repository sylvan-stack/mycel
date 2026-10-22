# One-time replacement of Mycel 1

This is an operator procedure with a read-only plan validator. Owner cutover and cleanup require their own explicit operator scope. No Arbol script, implementation, registry or instruction file is required. Source checkouts and historical document corpora are preserved. The development tool reads explicit JSON/evidence files and emits instructions; it has no cleanup executor, shell editor, database client or index-state importer.

Use Mycel's build and installation instructions in the [Build guide](builds.md). Preparation and accepted specifications alone do not supply a working release. Keep the previous command available until the new installed command and private database have actually been verified.

1. Observe the actual old runtime files, launchers, aliases and qualified old tables. Historical `~/bin/mycel`, `~/bin/better-grep` and `kn_` names are leads, not an inventory or wildcard authority. Record exact absolute canonical paths and separate schema/table names. A name or `owned: true` flag is insufficient. Bind independently inspectable release/source observations and their exact hashes; have the operator review what those observations establish. Keep uncertain objects blocked with a reason.
2. Qualify Mycel 2 and install its checked independent launcher. Use PostgreSQL tools to create a distinct new private database, then run explicit `mycel init`, local ingest and nonpaid checks. Copy no old vectors, edges, summaries, confirmations, history, settings rows or other index state. Paid `mycel embed` or live checks require their own explicit request; generating a plan never requests them.
3. Verify PATH and `mycel info` identify the new command, Build and new database, and update Mycel-owned caller instructions together. Only then remove exact verified old runtime files and manually remove inventoried alias definitions. The tool never edits a shell startup file. Group all inventoried definitions in one source file into one reviewed edit; preserve every other byte.
4. Immediately before legacy cleanup, obtain fresh ownership and catalog observations using PostgreSQL tools. Recheck exact OIDs, definitions, dependencies and the intended database. Review the generated transaction: explicit quoted table names, nonwaiting exclusive locks, OID guards and `DROP TABLE ... RESTRICT`. It drops no database and uses neither wildcards nor `CASCADE`. An uninventoried dependent object blocks the plan. The development tool never executes this SQL and Mycel 2 never connects to the old tables.
5. Verify old runtime/table absence, unchanged unrelated database objects, and surviving source/document corpora. Keep the observed verification and every failed or interrupted attempt. Before cutover, failure preserves the previous command. After committed cutover, record Mycel 2 availability and remaining cleanup; do not reconnect it to the old store or invent rollback/import work.

## Preparing the exact inventory

From the Mycel source root, with its prepared interpreter, these development
commands return one JSON result (`src` is the development import path):

```sh
PYTHONPATH=src python -m mycel_build replacement-plan --inventory /absolute/operator/inventory.json
PYTHONPATH=src python -m mycel_build replacement-validate --plan /absolute/operator/approved-plan.json --plan-sha256 EXACT_APPROVED_FILE_SHA256 --report /absolute/operator/report.json
```

Both commands are read-only. Save the `plan` and initial `report` objects from the first reply as separate files using your editor or ordinary operator tools. Independently review the exact plan file and retain its SHA-256; validation requires that approved file digest. A changed plan is refused even if someone recalculates its internal fingerprint. There is no `replacement-execute` command.

Inventory version 1 has exactly these fields: `schemaVersion`, `observedAt` (an aware timestamp), `oldDatabase` (`identity`, `catalog`), `newDatabase` (a distinct identity), `previousCommand`, `newCommand`, `files`, `aliases`, `tables`, and boolean `paidOperationsRequested`. A request recorded in an inventory is not authorization for a provider call. Observations more than one day old, changed evidence bytes, unsafe aliases, nonregular evidence, traversal and patterns are refused. No current owner paths or tables are filled in automatically.

Each file row contains `id`, `path`, `role`, `kind`, `sha256`, `ownership` and `uncertainty`. Kinds are `file`, `symlink`, `directory` or explicitly observed `absent`; a symlink hash covers its literal target, without following it. Directory and absent hashes are null; directory-wide cleanup is forbidden. Absent entries are restricted to runtime/launcher roles with null ownership/uncertainty, produce no removal step and must remain absent. Removal roles are `runtime` and `launcher`. `source_corpus`, `document_corpus`, `unrelated` and `uncertain` roles are preserved. A protected corpus root also protects nested proposed runtime targets, regardless of their historical names. Source/document directories retain a complete path/type/content fingerprint without following links; final verification compares that fingerprint. The previous command must be explicitly inventoried. A missing ownership record or uncertainty blocks removal instead of guessing.

Each alias row contains `id`, `name`, `sourceFile`, the exact single-line `definition`, `sourceSha256`, `ownership` and `uncertainty`. Alias edits are operator instructions. The plan binds the unchanged remainder's hash; report validation refuses an edit that changes uninventoried shell-file content.

Each table row contains separate `schema` and `name`, positive `oid`, `definitionSha256`, explicit `ownedDependents`, `ownership` and `uncertainty`. Identifiers are ordinary exact PostgreSQL identifiers, not qualified strings or patterns. An owned dependent is a separate schema/name object. The catalog evidence is strict JSON with `schemaVersion`, `observedAt`, `database`, complete observed `objects` and `dependencies`. Object rows contain `schema`, `name`, `kind`, `oid` and `definitionSha256`; dependency rows contain `owner`, `dependent` and boolean `automatic`. Include the full relevant dependency closure and unrelated objects whose survival must be verified. A finite fixture catalog is not an actual PostgreSQL observation.

A file binding is `{ "path": "/absolute/evidence-file", "sha256": "64 lowercase hexadecimal characters" }`. Ownership records are separately retained strict JSON: `schemaVersion: 1`, `observedAt`, `product: "mycel1"`, an exact `subject`, and a nonempty `basis` list. Each basis row contains an `artifact` binding, `locator` and factual `finding`. The file subject is its path/role/kind/hash; the alias subject is name/sourceFile/definition/sourceSha256; the table subject is database, exact catalog table object and exact owned dependent objects. A basis can point to ordinary text or JSON evidence. Evidence records and their basis must survive cleanup. Hash/shape checking binds what the operator inspected; it cannot infer historical ownership or replace human review of those facts.

## Verifying the step report

A report has `schemaVersion`, `planSha256` (the plan's internal body fingerprint) and the exact ordered `steps`. Each step has `id`, `status` (`pending`, `completed`, `blocked` or `failed`) and `verification`. Pending steps have null verification. Every other status binds a separately retained observation with `schemaVersion`, matching `planSha256`, `step`, `status`, `observedAt` and nonempty `facts`. A requested/completed flag without concrete matching evidence is refused.

Completed observations identify the exact reviewed inventory and complete `ownershipEvidence` list as `reviewedBasis`, working Build and launcher, new private database with actual init/ingest/nonpaid statuses, exact cutover command/info result, exact absent runtime paths, alias remainder, restrictive committed table transaction and fresh after-catalog, and verified surviving source objects. Explicit paid operations additionally bind separate request evidence and actual reports. The optional paid step stays pending when unrequested and supplies no provider proof.

The validator checks the completed prefix and reports observed committed effects even when a late failure leaves its step marked failed. It refuses later completion beyond an unfinished required step, cleanup before verified cutover, imported old state, changed approved plans, uninventoried file removal, changed shell content and lost unrelated catalog objects. It reports partial work and command availability from observations; it performs none of those actions. Retain raw PostgreSQL/command receipts and independently review the operator evidence before treating replacement as complete.

Unit rehearsals use actual disposable files plus an explicitly finite catalog executor. They establish plan/report boundaries, preservation and partial outcomes. A separately scoped operator rehearsal may additionally run the installed qualified Build and generated SQL against acknowledged disposable PostgreSQL databases, retaining real command/catalog receipts. That rehearsal is separate from automatic unit proofs, native release qualification and owner replacement. It never authorizes a real owner cutover or paid operation.

## Selecting the qualified release

Record the chosen Build's `build.json`, `checks.json`, program manifest and
independent launcher bundle before preparing a cutover. The reference release
for this procedure is version `2.0.0`, Build `1`, from source
`df1c1fb0add02d06fb80b3ea45ae402259838c79`, with source-input SHA-256
`e5b8a3114d785290b99ec70cfc552e46f0220c535574df421f3b637a11f487ab`.
Its launcher bundle digest is
`6e26434f86acc0eea68b0cc0ba5e5a63170263d16b82272dc4709094af6dfe54`.
A Build number is local to a registry; `1` in another registry proves nothing.
Check the actual working record, its complete required results and immutable
manifests. Retain their file digests in the operator record. Later development
changes do not change or inherit that installed Build's qualification.

The command is `~/.local/bin/mycel`, pointing into the independently verified
`~/.mycel/launcher/<bundle-digest>/` bundle; its selected program is under
`~/.mycel/builds/<number>/`. From the exact recorded source checkout, the
read-only development check is:

```sh
PYTHONPATH=src python -m mycel_build verify-source 1 --source /absolute/qualified-source --registry /absolute/home/.mycel/builds
```

It must return `matches: true`. A later source checkout correctly differs;
retain the original qualified source instead of modifying the Build record.
Recheck the command target and use `mycel -v 1 info` to pin the operator's
chosen Build. `-v` goes first. The unprefixed command may select a newer working
Build; verify both before cutover. Creating/installing/selecting a Build never
initializes the new store and never removes version 1. Development planning
commands run from Mycel's prepared source environment and are not installed
product commands.

## Operator worksheet and receipts

Keep the worksheet, inventories, approvals, SQL, backups, command outputs and
step observations outside source/document corpora. Separate rehearsal results
from actual owner replacement. Put the old and new server/database identities,
exact release bindings, observation time and operator scope in the worksheet;
the two database identities must differ. Never copy an old database address
into the new private settings accidentally.

For a rehearsal, PostgreSQL tools create two disposable databases whose names
start with `mycel_check_`, with creation acknowledgements retained. One contains
fictional legacy tables and unrelated sentinel objects; the other starts empty.
For an actual replacement, the old shared database remains in place. Removing
an acknowledged disposable test database after its rehearsal is test teardown,
not an instruction to drop the old shared database.

1. Record exact old file paths, literal symlink targets, alias definitions,
   hooks, protected source/document roots and all qualified legacy tables.
   Observe absent historical executable paths with `kind: "absent"`, null
   `sha256`, null `ownership` and null `uncertainty`, using only `runtime` or
   `launcher` roles. A dangling link is present. An absent entry never creates
   a removal step and must still be absent at final verification. If ownership
   or catalog completeness is unknown, stop with the uncertainty recorded.
2. Independently inspect the ownership basis and full relevant PostgreSQL
   dependency closure, including indexes, sequences, constraints and views.
   Record exact OIDs and stable definition hashes. A `kn_` prefix or historical
   table list is not ownership evidence. A non-automatic dependency outside the
   inventory blocks cleanup. Preserve unrelated rows, definitions, sequence
   state and source-tree fingerprints as comparison baselines.
3. Run `replacement-plan`, review its `blocked`, exact files/tables and
   `operatorSql`, save the plan/report separately and retain the approved plan
   file's SHA-256. A blocked plan has no SQL and cannot have completed steps.
   Planning/validation succeeding with exit 0 does not mean replacement is
   complete: inspect `complete`, `partial`, `remaining` and command availability.
4. Verify the chosen working Build and independent launcher. With PostgreSQL
   tools create the new private database, and prepare a separate settings file
   for fictional source/document roots in the rehearsal. Disable credential
   acquisition for the rehearsal with `[embedding] key_command =
   ["/usr/bin/false"]`. Use an outbound network restriction allowing only the
   disposable PostgreSQL server when available. Never request `--embed`, a
   real `embed`, `--live` or provider classification during automatic rehearsal.
5. Run the installed command explicitly against those new settings. For example,
   with a configured fictional repository named `fixture`:

   ```sh
   MYCEL_CONFIG=/absolute/operator/private.toml ~/.local/bin/mycel -v 1 init
   MYCEL_CONFIG=/absolute/operator/private.toml ~/.local/bin/mycel -v 1 ingest --repo fixture
   MYCEL_CONFIG=/absolute/operator/private.toml ~/.local/bin/mycel -v 1 status --repo fixture
   MYCEL_CONFIG=/absolute/operator/private.toml ~/.local/bin/mycel -v 1 refs --repo fixture
   MYCEL_CONFIG=/absolute/operator/private.toml ~/.local/bin/mycel -v 1 info
   ```

   Retain each actual exit code and JSON reply. `info` must identify the expected
   Build/version, selected settings, distinct database, supported store format
   and initialized store. Check local ingest/current source results and that no
   legacy tables or sentinel state reached the new database. No vectors,
   summaries, confirmations, edges, history or settings rows are imported.
   Keep the complete automatic requirement report for the chosen Build as the
   required nonpaid release checks; local command receipts verify the new store.
6. Verify the new command through a fresh shell's PATH and its `info` reply.
   In the rehearsal, command selection and `MYCEL_CONFIG` are limited to that
   process; no owner settings or shell files change. In an authorized actual
   cutover, the operator makes any reviewed shell/alias edit and preserves all
   other bytes. The tool performs no such edit. Caller instructions use one
   `mycel` command, `mycel grep` instead of `better-grep`, JSON replies for
   structured operations and the documented literal grep stream/exit contract.
7. After verified cutover, recheck each exact old file's type/hash/ownership
   immediately before its individual removal. Never delete a directory tree or
   follow a link target. Group aliases in each shell file into one reviewed
   operator edit. Retain observed absent-file and alias-remainder checks.
8. Before actual table removal, retain a PostgreSQL backup of exactly the
   inventoried tables and read it back to verify completeness. Obtain a fresh
   catalog/definition/dependency observation and compare it with the approval.
   Run only the reviewed generated transaction with PostgreSQL tools on the
   exact old database, with stop-on-error enabled. The transaction uses
   `LOCK TABLE ... NOWAIT`, exact OID guards and `DROP TABLE ... RESTRICT`.
   A busy lock, changed OID/definition or new dependency requires stopping and
   review; do not broaden the inventory, use `CASCADE` or drop the database.
9. Compare a fresh after-catalog and unrelated row/sequence/definition snapshots,
   verify every inventoried old runtime/table is absent, verify protected trees
   and evidence survive unchanged, and rerun the new command's `info`. Update
   the report from actual receipts and validate the exact approved plan. An
   optional unrequested paid step remains `pending` even when every required
   step is complete; it supplies no provider acceptance.

## Concrete inventory and report fields

This minimal inventory shape illustrates already absent programs and one
inventoried table. Replace the fictional database/path/OID/hash values with
fresh observations and expand `tables` to the complete exact list. A real
inventory must include every protected corpus and unrelated object needed for
verification. JSON has no comments; do not add fields such as `owned: true`.

```json
{
  "schemaVersion": 1,
  "observedAt": "2026-10-22T12:00:00+00:00",
  "oldDatabase": {
    "identity": "fixture-server/legacy",
    "catalog": {"path": "/absolute/operator/catalog-before.json", "sha256": "<catalog file SHA-256>"}
  },
  "newDatabase": "fixture-server/new-private",
  "previousCommand": "/absolute/old/bin/mycel",
  "newCommand": "/absolute/home/.local/bin/mycel",
  "files": [
    {"id": "old-mycel", "path": "/absolute/old/bin/mycel", "role": "runtime", "kind": "absent", "sha256": null, "ownership": null, "uncertainty": null},
    {"id": "old-grep", "path": "/absolute/old/bin/better-grep", "role": "launcher", "kind": "absent", "sha256": null, "ownership": null, "uncertainty": null}
  ],
  "aliases": [],
  "tables": [
    {"schema": "legacy", "name": "kn_chunks", "oid": 12345, "definitionSha256": "<definition SHA-256>", "ownedDependents": [], "ownership": {"path": "/absolute/operator/kn-chunks-ownership.json", "sha256": "<ownership file SHA-256>"}, "uncertainty": null}
  ],
  "paidOperationsRequested": false
}
```

Use actual independently inspectable ownership JSON described above. For
example its table `subject` is `{database, table, ownedDependents}`, where
`table` is the exact catalog object including `kind: "table"` and each owned
dependent is its full observed catalog object. Each `basis` item binds a
retained artifact by `{path, sha256}` plus `locator` and factual `finding`.
Do not use an object scheduled for cleanup as the only ownership basis.

The initial report from the planner supplies the exact ordered step IDs; keep
that order. Every nonpending row binds a separate observation file with this
shape (the digest strings below are placeholders for real computed hashes):

```json
{
  "schemaVersion": 1,
  "planSha256": "<plan internal body SHA-256>",
  "step": "new_private_store",
  "status": "completed",
  "observedAt": "2026-10-22T12:10:00+00:00",
  "facts": {
    "database": "fixture-server/new-private",
    "initExitCode": 0,
    "localIngestExitCode": 0,
    "nonpaidChecksExitCode": 0,
    "copiedVersion1State": []
  }
}
```

The report row's `verification` is that observation's `{path, sha256}` binding.
The observation binds these concrete facts for each step:

| Step | Required facts for completion |
|---|---|
| `inventory_review` | `inventorySha256`, empty `uncertainObjects`, and the exact plan's complete `ownershipEvidence` list as `reviewedBasis` |
| `qualification_and_launcher` | `workingBuild` binding to the actual working record, and `launcher` equal to `newCommand` |
| `new_private_store` | Exact `database`, zero `initExitCode`, `localIngestExitCode`, `nonpaidChecksExitCode`, and empty `copiedVersion1State` |
| `command_cutover` | Exact `command` and `database`, zero `infoExitCode`, and observed `cutoverCommitted` |
| `remove_file:<id>` | Exact `path`, `beforeSha256`, and observed `after: "absent"` |
| `remove_alias:<group-id>` | Exact `sourceFile`, `beforeSha256`, `editCommitted`, and actual unchanged-remainder hash |
| `remove_old_tables` | Exact ordered `removedTables` schema/name pairs, `restrict: true`, `transactionCommitted: true`, and fresh `catalogAfter` binding |
| `verify_survivors` | Fresh `catalogAfter`, `unrelatedObjectsVerified: true`, `sourceCorporaVerified: true`, with all actual preserved files/trees unchanged |

Retain raw command, backup, SQL and before/after receipts alongside these facts.
The validator binds their declared observations; it cannot authenticate their
meaning, prove exhaustive catalog capture or turn asserted exit codes into
executed commands. The operator must independently inspect those receipts.

For a failed/interrupted step, record its actual status, failure and observed
committed effects; leave later required steps pending. For example a failed
`remove_old_tables` after a transaction committed still binds the exact table
list, `restrict`, `transactionCommitted` and after-catalog. Validation then
reports those effects, `complete: false`, `partial: true` and the verified new
command. A failure before cutover preserves the observed previous command;
when that command was already absent, availability is `unverified`. Never
manufacture a previous executable or reconnect the new Build to the old store.
Keep every attempt and issue a new receipt when retrying; no failed evidence
is overwritten.

<!-- sources:
mycel:@code/src/mycel_build/_replacement.py#replacement_plan
mycel:@code/src/mycel_build/_replacement.py#validate_replacement_report
mycel:@code/src/mycel_build/__main__.py#main
mycel:@code/tests/test_replacement.py#ReplacementTests
-->
