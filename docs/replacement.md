# One-time replacement of Mycel 1

This is an operator procedure and a privately prepared plan validator. It has not replaced an owner's installation or opened a legacy database. No Arbol script, implementation, registry or instruction file is required. Source checkouts and historical document corpora are preserved. The development tool reads explicit JSON/evidence files and emits instructions; it has no cleanup executor, shell editor, database client or index-state importer.

Use Mycel's build and installation instructions in the [Build guide](builds.md). Preparation and accepted specifications alone do not supply a working release. Keep the previous command available until the new installed command and private database have actually been verified.

1. Observe the actual old runtime files, launchers, aliases and qualified old tables. Historical `~/bin/mycel`, `~/bin/better-grep` and `kn_` names are leads, not an inventory or wildcard authority. Record exact absolute canonical paths and separate schema/table names. A name or `owned: true` flag is insufficient. Bind independently inspectable release/source observations and their exact hashes; have the operator review what those observations establish. Keep uncertain objects blocked with a reason.
2. Qualify Mycel 2 and install its checked independent launcher. Use PostgreSQL tools to create a distinct new private database, then run explicit `mycel init`, local ingest and nonpaid checks. Copy no old vectors, edges, summaries, confirmations, history, settings rows or other index state. Paid `mycel embed` or live checks require their own explicit request; generating a plan never requests them.
3. Verify PATH and `mycel info` identify the new command, Build and new database, and update Mycel-owned caller instructions together. Only then remove exact verified old runtime files and manually remove inventoried alias definitions. The tool never edits a shell startup file. Group all inventoried definitions in one source file into one reviewed edit; preserve every other byte.
4. Immediately before legacy cleanup, obtain fresh ownership and catalog observations using PostgreSQL tools. Recheck exact OIDs, definitions, dependencies and the intended database. Review the generated transaction: explicit quoted table names, nonwaiting exclusive locks, OID guards and `DROP TABLE ... RESTRICT`. It drops no database and uses neither wildcards nor `CASCADE`. An uninventoried dependent object blocks the plan. The development tool never executes this SQL and Mycel 2 never connects to the old tables.
5. Verify old runtime/table absence, unchanged unrelated database objects, and surviving source/document corpora. Keep the observed verification and every failed or interrupted attempt. Before cutover, failure preserves the previous command. After committed cutover, record Mycel 2 availability and remaining cleanup; do not reconnect it to the old store or invent rollback/import work.

## Preparing the exact inventory

The development commands return one JSON result:

```sh
python -m mycel_build replacement-plan --inventory /absolute/operator/inventory.json
python -m mycel_build replacement-validate --plan /absolute/operator/approved-plan.json --plan-sha256 EXACT_APPROVED_FILE_SHA256 --report /absolute/operator/report.json
```

Both commands are read-only. Save the `plan` and initial `report` objects from the first reply as separate files using your editor or ordinary operator tools. Independently review the exact plan file and retain its SHA-256; validation requires that approved file digest. A changed plan is refused even if someone recalculates its internal fingerprint. There is no `replacement-execute` command.

Inventory version 1 has exactly these fields: `schemaVersion`, `observedAt` (an aware timestamp), `oldDatabase` (`identity`, `catalog`), `newDatabase` (a distinct identity), `previousCommand`, `newCommand`, `files`, `aliases`, `tables`, and boolean `paidOperationsRequested`. A request recorded in an inventory is not authorization for a provider call. Observations more than one day old, changed evidence bytes, unsafe aliases, nonregular evidence, traversal and patterns are refused. No current owner paths or tables are filled in automatically.

Each file row contains `id`, `path`, `role`, `kind`, `sha256`, `ownership` and `uncertainty`. Kinds are `file`, `symlink` or `directory`; a symlink hash covers its literal target, without following it. Directory hashes are null and directory-wide cleanup is forbidden. Removal roles are `runtime` and `launcher`. `source_corpus`, `document_corpus`, `unrelated` and `uncertain` roles are preserved. A protected corpus root also protects nested proposed runtime targets, regardless of their historical names. Source/document directories retain a complete path/type/content fingerprint without following links; final verification compares that fingerprint. The previous command must be explicitly inventoried. A missing ownership record or uncertainty blocks removal instead of guessing.

Each alias row contains `id`, `name`, `sourceFile`, the exact single-line `definition`, `sourceSha256`, `ownership` and `uncertainty`. Alias edits are operator instructions. The plan binds the unchanged remainder's hash; report validation refuses an edit that changes uninventoried shell-file content.

Each table row contains separate `schema` and `name`, positive `oid`, `definitionSha256`, explicit `ownedDependents`, `ownership` and `uncertainty`. Identifiers are ordinary exact PostgreSQL identifiers, not qualified strings or patterns. An owned dependent is a separate schema/name object. The catalog evidence is strict JSON with `schemaVersion`, `observedAt`, `database`, complete observed `objects` and `dependencies`. Object rows contain `schema`, `name`, `kind`, `oid` and `definitionSha256`; dependency rows contain `owner`, `dependent` and boolean `automatic`. Include the full relevant dependency closure and unrelated objects whose survival must be verified. A finite fixture catalog is not an actual PostgreSQL observation.

A file binding is `{ "path": "/absolute/evidence-file", "sha256": "64 lowercase hexadecimal characters" }`. Ownership records are separately retained strict JSON: `schemaVersion: 1`, `observedAt`, `product: "mycel1"`, an exact `subject`, and a nonempty `basis` list. Each basis row contains an `artifact` binding, `locator` and factual `finding`. The file subject is its path/role/kind/hash; the alias subject is name/sourceFile/definition/sourceSha256; the table subject is database, exact catalog table object and exact owned dependent objects. A basis can point to ordinary text or JSON evidence. Evidence records and their basis must survive cleanup. Hash/shape checking binds what the operator inspected; it cannot infer historical ownership or replace human review of those facts.

## Verifying the step report

A report has `schemaVersion`, `planSha256` (the plan's internal body fingerprint) and the exact ordered `steps`. Each step has `id`, `status` (`pending`, `completed`, `blocked` or `failed`) and `verification`. Pending steps have null verification. Every other status binds a separately retained observation with `schemaVersion`, matching `planSha256`, `step`, `status`, `observedAt` and nonempty `facts`. A requested/completed flag without concrete matching evidence is refused.

Completed observations identify the exact reviewed inventory and complete `ownershipEvidence` list as `reviewedBasis`, working Build and launcher, new private database with actual init/ingest/nonpaid statuses, exact cutover command/info result, exact absent runtime paths, alias remainder, restrictive committed table transaction and fresh after-catalog, and verified surviving source objects. Explicit paid operations additionally bind separate request evidence and actual reports. The optional paid step stays pending when unrequested and supplies no provider proof.

The validator checks the completed prefix and reports observed committed effects even when a late failure leaves its step marked failed. It refuses later completion beyond an unfinished required step, cleanup before verified cutover, imported old state, changed approved plans, uninventoried file removal, changed shell content and lost unrelated catalog objects. It reports partial work and command availability from observations; it performs none of those actions. Retain raw PostgreSQL/command receipts and independently review the operator evidence before treating replacement as complete.

Private unit rehearsals use actual disposable files plus an explicitly finite catalog executor. They establish plan/report boundaries, preservation and partial outcomes. They are not an owner cutover, a real PostgreSQL deployment rehearsal or a pinned-release qualification. A generated-store check would need its own `store` declaration and a separately reviewed execution scope before any later run.

<!-- sources:
mycel:@code/src/mycel_build/_replacement.py#replacement_plan
mycel:@code/src/mycel_build/_replacement.py#validate_replacement_report
mycel:@code/src/mycel_build/__main__.py#main
mycel:@code/tests/test_replacement.py#ReplacementTests
-->
