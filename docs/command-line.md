# Command line and settings

This checkout implements the SYL-98 command boundary, SYL-99 strict settings and SYL-100 repository resolution/listing. Start it with `PYTHONPATH=src python3 -m mycel --help`, or install its `mycel` console command in a development environment. `info` reports settings/store diagnostics, `repos` lists configured repositories, `init` creates or explicitly changes the private store, `refs` reports retained declarations and faults, `derive` asserts or withdraws one guarded dependency selection, `relate` asserts or withdraws one exact directed relation, `confirm` records exact guarded verification, `justify` states an Origin Link with verification, `origins` reports Origin Coverage, `recovery` judges local Origin candidates and reviews model claims, `verifications` lists applicable records or retained history, `ingest` publishes complete scoped captures and their dependency/detection/collection changes, `activity` lists ordered history and reads exact entry details, `embed` runs finite scoped embedding, `evaluate` validates evaluation files, measures retrieval through normal search and exercises non-live Drift fixtures, `read` returns one current indexed chunk, `search` returns evidence-bearing schema3 results, `undocumented` lists code without describing sections, `overview` prints stored code directory outlines, `classify` explicitly executes bounded classification, `drifts`, `stale` and `status` report local provenance, and `grep` can append a read-only related search after literal system grep. Other accepted feature commands return `settings` when preflight fails, then `refused` until their implementation tasks supply handlers. A numbered staged package adds its lowercase hexadecimal `build` to `info` and records activity for actual mutations, including initialization and ingest. Unnumbered source development has no Build number and deliberately records no activity; a numbered package with a missing or damaged identity fails with `internal`. A changing ingest has one activity entry for its repository with the exact reply counts and file/identity details; a no-op has none. The independent installed launcher selects numbered Builds; see the [Build guide](builds.md) for installation, explicit selection and maintenance. No unavailable command returns an empty success reply. The [settings guide](settings.md) describes the complete validated schema, defaults and reviewer setup. The [store guide](store.md) describes configured acceptance for initialization, compatibility and connection-owned guards.

Help is one JSON object and works without settings. Use `--help` or `-h`, or `<command> --help` for a reserved command. With no arguments, Mycel returns help. The scope boundary preserves repeatable literal `--repo <name>` selections; `ingest`, `embed`, `classify`, `status` and `activity` also accept `--all`. Combining both is invalid. An absent selection resolves from the longest configured folder containing the current directory. Configured `code_clones` are locations of the same repository; a command inside one uses its checkout and policy. `readonly_root` selects the retained `main` baseline for Origin Coverage changes. Organization selectors and directories outside their member folders expand to enabled configured members; explicit repository selection preserves exact names. Folder faults affect the selected repository alone. The resolver has no special repository aliases; MYC-D37 explicitly permits only the prescribed named shared selections and scan exclusions as packaged data. Option abbreviation and unknown options are invalid.

Each ordinary invocation writes exactly one JSON document with a final newline. Success exits 0. Failure exits 1 with `{ "error": { "code": "refused", "message": "…" } }` or another code in the closed list below. Caller interruption exits 2 with `refused` and `Stopped by the caller.` Diagnostics go to standard error, without raw exception details. Serialization completes before output starts, using ASCII-safe JSON escapes for text. A closed output receiver returns status 1 with a diagnostic; no second result is appended to partial output. Selected repositories each retain their result or closed error, including a single refused repository or an entirely refused scope; any refused member sets exit 1. The common envelope is `{repositories: [{repository, result | error}]}`. Settings, syntax, unresolvable CWD and shared store-preflight faults that precede individual work remain top-level errors. Feature progress replies retain their documented repository maps and interrupted counts.

The installed launcher accepts `-v <number>` only as the first two arguments, removes them and passes every remaining argument unchanged. Its default is the highest intact compatible working Build; an explicitly named withdrawn Build runs with its reason on standard error. An unknown or malformed number returns `invalid_input`, an unavailable known Build returns `refused`, and a held distribution lock returns `busy`. Direct source execution has no numbered registry selection and returns `refused` for the otherwise valid reserved prefix. `grep` keeps its raw arguments and streamed-result boundary; the common boundary adds no JSON to its output.

## Setting API keys

Run `mycel api-key voyage` or `mycel api-key jev` from a terminal with valid settings. The prompt hides what you type. Mycel creates or replaces the corresponding generic password in the login Keychain and returns, for example:

```json
{"stored":"voyage","item":{"service":"mycel","account":"voyage-api-key"},"replaced":false}
```

The command takes only the provider name. Do not put a key in an argument or pipe it into standard input. Missing terminal access, empty or non-printable-ASCII input, or a key too long for secure native input returns `invalid_input`; a failed Keychain write returns `refused`. It does not open the index store or call a provider. The existing `embedding.key_command`, when configured, still takes precedence over the stored Voyage key for embedding.

macOS can ask for permission when replacing an item's access rules. This is the login Keychain's native approval, separate from the hidden API-key prompt. A refusal or timeout returns no success; the key may already have changed before an access-rule update fails. The command never reads the previous key to determine whether it replaced an item.

## Grep and its related search tail

`mycel grep` starts the first `grep` on PATH before loading settings or opening
a store. Every argument after `grep`, including `--help`, `--repo` and `-v`,
is passed literally, in order: Mycel adds no implicit path or option. Grep owns
standard input, output and error. Its output remains the exact prefix before
any marked tail; its exit status remains the command's status. Grep runs when
settings are missing/invalid, no repository is found or the store is unavailable.

After grep finishes with status 0 or 1, an eligible invocation can append the
ordinary combined code/document search, including selected shared documents,
with at most five results. Query preparation follows normal search rules;
unavailable meaning search can return wording results. The lookup uses
`no_fresh=True`: it performs no freshness pass and writes no ingest, vectors,
activity, pins or cache to the store. It never embeds corpus content or runs
classification. It can prepare one query vector through the normal provider.

| Case | Related tail |
|---|---|
| `MYCEL_GREP_PLAIN=1` | None; no tail settings or services are accessed |
| Grep exits above 1, including its own error | None |
| Count, filename-only or quiet mode (`-c`, `-l`, `-L`, `-q`, and long forms) | None |
| Patterns come from `-f` or `--file` | None |
| An unknown option, missing option value, no pattern, help or version output | None |
| Fewer than three non-whitespace characters remain after regexp signs are removed | None |
| First-path/CWD scope is outside an enabled repository, or is an organization | None |
| An otherwise eligible tail encounters invalid settings, unavailable store or another search failure | None; one sanitized diagnostic line on standard error |
| Search has no results | None |

Pattern extraction understands value-taking options, attached values such as
`-A3` and `--regexp=needle`, short clusters such as `-rn`, and `--` ending options.
The first `-e`/`--regexp` supplies the query; otherwise the first operand does.
Other operands remain paths, even when they precede an explicit `-e`. Options
are interpreted only to decide the tail, never to rewrite grep's arguments.
An expression with no regexp sign other than `.` stays exact, so
`session.renew` remains one query. Other regexp signs become word separators.

The first path determines the repository even when the current directory or
later paths belong elsewhere. With no path, or a first stdin operand `-`, Mycel
uses the current directory. It resolves the actual path through configured
folder bindings. The longest binding wins; an actual repository wins an equal
length tie with an organization. A more specific organization folder suppresses
the tail, even if the organization has only one member. A first path outside
repository scope never falls back to the current directory or another path.

The tail starts with `── mycel: related search results (not grep output) ──`.
If meaning search fell back, the header instead says `(wording only)`; it does
not label wording results as meaning matches. Each result prints its qualified
place, code line span when present and the section that supplied a bridge.
The `documented in` block names each cited/bridging section once. Stale sections
carry `⚠ stale`, Heartwood sections carry `[heartwood]`, and no score is printed.
Place text is escaped onto single lines. A newline separating the marked tail
belongs to the tail, including when grep ended without a newline.

Any optional query, store, rendering, output or tail-cancellation failure keeps
grep's completed status and attempts one diagnostic line; it never replaces
grep's output with a JSON error. Use `MYCEL_GREP_PLAIN=1` when a caller requires
only grep bytes. Call `mycel search` for a structured result.

<!-- sources:
mycel:@code/src/mycel/_cli.py#_plain_grep
mycel:@code/src/mycel/_cli.py#run
mycel:@code/src/mycel/_grep.py#parse_grep_args
mycel:@code/src/mycel/_grep.py#semantic_query
mycel:@code/src/mycel/_grep.py#resolve_tail_repository
mycel:@code/src/mycel/_grep.py#search_tail
mycel:@code/src/mycel/_grep.py#render_tail
mycel:@code/src/mycel/_grep.py#append_tail
-->

## Other command behavior

Model and subprocess boundaries are internal. Allowed service purposes are explicit and dry-runs deny all service calls. Ingest may embed only when explicitly requested; searches may embed their queries; neither may classify or review dependencies. Classification and live drift evaluation may use Jev and the configured reviewer; summaries build/regenerate may use the configured writer and embedding. Child environments omit parent credentials and store addresses. Git operations are restricted to validated read-only forms.

`mycel repos` reads settings only and returns `organizations` (name, checkout root, document root) and `repositories` (exact name, enabled state, optional organization, code/document folders with repository/organization provenance, and optional local fault). Disabled and faulty entries remain visible.

`mycel info` reports all settings faults without refusing them or echoing invalid values. With valid settings it adds configured embedding model/dimensions, the exact classification model and reviewer identity, without probing the reviewer or acquiring model credentials. Store diagnostics use a read-only snapshot and report unavailable, empty, foreign, older, damaged or newer stores without changing them.

`mycel repos remove <name> [<name> ...]` removes indexed state for each exact name, including disabled and orphan repositories. Repeated names run once. Each repository is one atomic transaction under the existing nonblocking removal guard; live passes, embedding, classification, summaries and evidence mutations make that member `busy`. Source checkouts and artifact files remain untouched. Each `result` reports `repository`, `known` and `removed` counts for documents, chunks, versions, vectors, edges, evidenceBlobs, evidenceManifests, drifts and verifications. Other repositories retain their independent evidence, pins and index state. Configured empty names succeed with zero counts; unknown names without indexed rows return `unknown_repository`. Numbered Builds record global removal activity with the feature transaction. A final audit/connection fault preserves acknowledged removed counts with `countsState: "committed_prefix"` and a sanitized error.

Evaluation takes one enabled repository and returns one report; organizations and repeated selectors are refused. Non-live Drift evaluation uses deterministic Jev/reviewer stand-ins with the production finite routing and evidence lifecycle. It changes only invocation-local fixture state and reports simulated, unqualified outcomes. Interruption exits 2, other unfinished work exits 1, and a completed unqualified report exits 0. Explicit `--kind drift --live` selects the configured-provider fixture pipeline. Missing reviewer or Jev configuration produces an unqualified no-call report; complete unqualified reports retain status 0, interruption status 2, and unfinished work status 1. See the [evaluation guide](evaluation.md) for the exact file schema, null empty reports, normal retrieval measurement and explicit on-demand proof requirements.

`mycel search <query> [--repo <name>] [--k 1..100] [--only code|docs]
[--no-fresh]` returns schema3 results with canonical root-aware addresses,
stale source/path reasons, Heartwood and exact-version dependency-check faults
on results and their citations. It returns one full reply per enabled selected
member. A single repository returns SearchReply directly; organization scope
wraps replies as `{schema: 3, organization, repositories: [...]}` and other
multiple selections as `{schema: 3, repositories: [...]}`. Query embedding
failure preserves wording results with `meaning: {used: false, reason}`.
`freshness` reports required repository completion, committed ingest counts and
result-scope versions without full current-model coverage. `--no-fresh` leaves
all checks incomplete. The [retrieval guide](retrieval.md) defines fields,
ranking routes and the bounded query/freshness boundary. Use `--` before an
option-shaped query.

`mycel undocumented [--repo <name>] [--path <path>]... [--no-fresh]` returns
`{repository, paths, chunks, freshness}` for one enabled repository. It lists
current disk code that no document section describes through a direct declared
or asserted dependency in either direction, sorted by root, path and name.
Relative path filters are repeatable and match a file or directory descendants.
It uses the ordinary bounded search freshness check; `--no-fresh` reads stored
state without writes. It makes no link or model request. Code search results
include query-independent `described`; read replies include complete
`documents` links with section, direction and edge kind. The
[retrieval guide](retrieval.md#complete-document-links-and-undocumented-code)
explains the difference from the query-ranked `documentedIn` citations.

The internal [Drift work lifecycle](drifts.md) opens local exact-pair work after
mechanical detection and closes only answered reasons. It preserves stale
marks, baseline pins and verification history across categorical results.
`mycel classify [--repo <name> | --all] [--k <pairs>] [--dry-run]`
explicitly runs a finite, capped classification invocation. Complete local
eligibility and exact request inputs govern deterministic selection. A repository
classification lock remains live through every attempt; pass locks and writing
transactions end before HTTP or reviewer process work. Transient retries share
the original invocation deadline. Completed applications survive later faults,
busy results, deadlines and interruption, with a partial reply per repository.
A successful support judgement closes only the answered work and preserves
stale marks, pins and verifications. Dry-run reports exact stage byte counts,
eligibility, reviewer readiness and maximum calls without acquiring credentials,
launching the reviewer or writing state/activity. A dry-run reaches the store with its ordinary password policy; it takes no
Jev, reviewer or Voyage credential.

`mycel drifts [--repo <name>] [--closed] [--all-versions]` reads current open
work. The optional filters include closed current work or inactive exact versions
with their stored locations. Work bundles, exact source pairs, stage counts,
judgements, unresolved faults and inactive versions remain separate.
`mycel stale [--repo <name>]` returns every retained current stale chunk and
all source/path reasons, including applicable classification evidence.
`mycel status [--repo <name> | --all]` reports each repository's `known`,
`enabled`, configured `folders`, documents/chunks `onDisk` and branch/stash-only
`elsewhere`, current stale chunks, version `vectors` and input `parts` coverage,
and optional `lastPass`. Embedded versions require complete coverage for the current configured
model/dimensions. Pending parts are exactly an ordinary next embed would send;
disabled and unknown repositories have no pending work. Incomplete ineligible
versions appear separately as `vectors.ineligible`, and durable uncommitted
results as `deferred`. Retained branch/stash versions participate in coverage. Valid unresolved and invalid
references and separate Drift counts remain available. `--all` includes every
indexed name, including disabled and missing settings entries. Named stored
orphans can be inspected directly. Reporting does not require source folders or
run filesystem scans, freshness, provider work, evidence collection or writes.
Every member reads the same committed repeatable-read snapshot.
See the [classification guide](classification.md) and [Drift guide](drifts.md).

`summaries` accepts `--dry-run`. Actual `build` and `regenerate` validate the
configured writer and prompt overrides before feature dispatch.
An absent writer returns `settings`; dry runs and report/removal preflight need
no writer. Actual build stages complete generated levels and real vectors
privately, then atomically replaces the tree after final source/settings checks.
Regeneration repairs stale members lowest-first in their existing places,
retains independent committed successes and blocks parents of stale members.
Removal atomically deletes the current set and returns its actual removed count.
The [summary guide](summaries.md) describes lifecycle guards and complete replies.

The contract below is checked against dispatch declarations. Change it in the same change as commands, common options or reply shapes. Feature handlers must extend their command guide and passing checks as they land. The complete 333-requirement registry and staged/release coverage gates distinguish accepted specifications from executed checks; unimplemented requirements remain pending. A release gate fails while any required proof is missing. Store proofs require an individually created and discarded `mycel_check_` database with private settings; mock store backends do not establish PostgreSQL acceptance.

`mycel refs [--repo <name>] [--unresolved]` reads retained source declarations in one store snapshot. It returns each owning chunk with a portable address, original declaration and line, current resolution or fault, qualified ambiguity candidates, and separate baseline status. `--unresolved` selects resolution faults. Reporting does not retry refs or require their folders to be present. Explicit repository selectors preserve local selection errors alongside successful reports. The command writes no feature rows or activity.

`mycel derive [--remove] <dependant> <source>` takes one current on-disk dependant chunk first and a source file, chunk or class family second. Both repositories must be registered and enabled. Resolve and validate the entire selection before committing an asserted dependency and its exact evidence. Declared dependencies and unrelated assertions retain their rows, edges, faults and pins. Repeating an identical selection, including a qualified/legacy alias, preserves its baseline and creates no activity. `--remove` withdraws only the matching assertion; a retained away/deleted source can still be withdrawn. Removing an absent assertion succeeds without mutation. If that missing source never had a selected assertion, `source` is null and `sourceRef` preserves the literal input rather than guessing a root. The reply otherwise names qualified `dependant` and `source` places, exact `dependantVersion`, `action`, `changed`, `members` and, for an assertion, `baselineManifest`.

The command rereads complete dependant and source files, settings and relevant retained Git locations under the repository guards, including a final check after activity attachment. Changed-since-ingest inputs return `invalid_input` with `changed_since_ingest` and qualified affected addresses; ingest explicitly before retrying. Self/circular expanded selections return `invalid_input` with `dependency_cycle`. Numbered Builds commit actual `derive` activity with the feature writes and exact final reply. Derive does not ingest or renew an existing pin. Complete ingest uses the same guarded APIs. Stale reporting retains every mechanical reason; generated publication has its own guarded evidence contract.

`mycel relate [--remove] <dependant> <source>` takes two current disk chunks, dependant first. Class endpoints mean headers alone; file-wide and index-only endpoints are invalid. Each direction is explicit, cycles are permitted, and relations grant no authority or role. Assertions retain independent ownership from related comments; identical assertions and absent removals leave pins, evidence and activity untouched. Removal can select a retained missing source. Exact source/settings/capture checks and final audit guards match derive. The reply contains `dependant`, `dependantVersion`, `source`, `action`, `changed`, `members` and an asserted `baselineManifest`; an absent unowned source returns `source: null` with `sourceRef`. The [relation guide](relations.md) describes complete declared selections, visible faults and direct-only mechanical warnings. Declared relation entries in `refs` add `kind: "related"` while keeping every original occurrence.

`mycel confirm <dependant> [--by <name>] [--how read|check]` confirms one current on-disk chunk. A class endpoint means its header; file-wide and index-only endpoints are refused. `--by` defaults to the invoking login name and `--how` defaults to `read`. Complete dependency and relation selections are reread under nonblocking guards, their permitted pins are renewed, and the verification evidence and numbered-Build activity commit together. Source-free chunks can be confirmed. Generated text is refused. Changed-since-ingest inputs return qualified `invalid_input` with `changed_since_ingest`; ingest explicitly and retry. New malformed, ambiguous, disabled or unresolved references refuse without writes. Confirmation may withdraw a previously resolved deleted source; a declaration that still names it remains a fault. Remaining upstream staleness still applies.

`mycel justify <chunk> <origin> [--by <name>]` resolves one current disk chunk and a complete Origin selection by Entity URI or ordinary address. In one guarded transaction it asserts the dependency, records `method: "stated"`, `confidenceScore: 1`, `confidence: "asserted"`, who and when, and confirms the exact dependant version. Entity Origins are written as URIs; other Origins use canonical addresses. Generated, unresolved and changed-since-ingest inputs refuse without feature writes. `mycel justify --file <pairs.jsonl> [--by <name>]` accepts one exact `{ "chunk": "…", "origin": "…" }` object per nonempty line. All pairs resolve before writes and the complete batch commits or rolls back together. `refs` exposes the statement with `kind: "asserted"` and `originLink`; `stale` and `verifications` read its ordinary policy and verification. A link remains a claim.

`mycel origins [<chunk>] [--repo <name>] [--missing] [--path <path>] [--changes] [--unresting] [--no-fresh]` reports one repository's current chunks and links. Paths repeat and match component boundaries. Normal use runs one scoped ingest, without embedding or a model; `--no-fresh` reads only the store. `--changes` queries disk versions absent from retained local `main` in `readonly_root`, requiring that baseline to have been ingested. `--unresting` also lists requirements and decisions without a dependant. `origins --needs-nothing <requirement> --reason <text>` suppresses a requirement from that list with its explanation; `--clear-needs-nothing <requirement>` withdraws the mark. Listings return 0 whatever they contain. The [Origin Coverage guide](origins.md) gives examples and reply shapes.


The `Verification` reply contains `id`, qualified `chunk`, logical `chunkId`, exact content `version`, `textHash`, verification-owned `dependantSnapshot`, immutable `baselineManifests`, every checked source/related member's qualified `place`, exact `hash`, pin `comparisonHash` and retained `snapshot`, and `by`, `how`, `at`, `current`. The exact content version is the text digest scoped to that logical chunk; internal database row identifiers are not public version identities. Record-owned evidence survives later repinning, source removal and collection of an old dependant version.

`mycel verifications [--repo <name>] [--history]` reads one enabled repository, selected explicitly or from CWD; organizations and repeated selectors are invalid. It returns `{repository, verifications}` with the newest applicable record for each exact current disk dependant version. `--history` includes all retained records with their `current` flags. Applicability requires exact dependant/source bytes and selection membership; changed, missing or uncheckable inputs make it false. Records have no expiry and vouch for the checked state without certifying upstream claims. Sort by canonical root, path and name, then newest time and record ID. Empty lists succeed. Listing uses one read-only snapshot, runs no freshness pass, writes no feature/activity rows and calls no provider. History lasts until the logical chunk or repository is deleted. The [relation and verification guide](relations.md) explains evidence and retention.

`mycel embed [--repo <name> | --all] [--dry-run] [--retry-failed]` embeds retained exact versions only in the named/CWD scope. Repository folders are used for scope resolution; retained inputs require no scan. `--retry-failed` selects failures explicitly while preserving successful vectors. `--dry-run` reports provisional exact version/part selection, token estimates including repeated place lines, and planning failures without service calls, embedding credentials, writes or receipt drains. The reply contains `model`, `dimensions`, `planner` provenance and a `repositories` object keyed by literal repository name. Each result contains version `sent`, `embedded`, `pending`, `failed`, `deferred` and separate `parts` counts; local errors remain beside other results. Dry runs add per-repository selection/fault details and an invocation `estimate`. Pending counts describe an ordinary next pass even when retry selection is requested. Paid deferred results have separate counts and publish before any new send in a later pass. Partial versions never count as embedded.

After any repository work starts, interrupted/stopped embedding retains committed batch progress and returns `stopped="interrupted"` with exit 2 or `stopped="gave_up"` with exit 1 and sanitized local errors. When every initial capture/plan read fails before work starts, the common envelope retains each selected repository's error; an interruption before work starts uses the common stopped reply with exit 2. Completed dry-run preparation, including empty results or local planning failures, keeps the full per-repository report. An unavailable/interrupted final recount is labeled `countsState="committed_prefix"`, preserving acknowledged progress without claiming a fresh full inventory. A settings change prevents further sends and late publication; disabled or removed repositories have no pending work. Numbered Builds record actual embedding mutations with final reply counts; empty passes and dry runs leave no activity entry. The [embedding guide](embedding.md) gives the complete planning, persistence and progress rules.

`mycel summaries [status] [--repo <name>]` reads one enabled repository's stored summary levels and disjoint section membership/embedding counts. `mycel summaries build|regenerate --dry-run [--repo <name>]` returns complete ordered plans without freshness, writer, embedding, store mutations or activity. Organizations and repeated repository selectors are refused. Build plans use the pinned `mycel-summary-v1` profile, bounded exact leaf requests and explicitly estimated higher-level mean vectors/requests. Regeneration keeps stored membership and reports writes, missing-member removals and stale-member blockers. Empty scope results succeed. Actual summary build stages whole writer responses, embeds each level before grouping the next, and replaces the tree atomically after exact final guards; failures or changed inputs preserve the old set. Empty eligible replacement retains set metadata. The reply counts notEmbedded sections. Actual regeneration atomically publishes each stale summary with current vectors and pins, lowest-first in its existing place, retaining independent successes and blocking parents of still-stale generated members. `summaries remove` deletes the current set and its generated ownership atomically and succeeds with zero on empty scope. Missing generation configuration is checked before a real build/regeneration. The [summary guide](summaries.md) describes profile, eligibility, stored metadata and lifecycle replies.

`mycel activity [--repo <name> | --all] [--kind <kind>] [--k <count>]` lists
summary entries newest first by start time and ID, default 25 and capped at 500.
A positive decimal count and known kind are required. Select one repository
explicitly or from its folder; `--all` includes global, disabled and orphan
history. `mycel activity --entry <id>` reads exact file, identity and classification
details and is exclusive with all listing filters. Missing/pruned entry IDs use
`refused`, as clarified by the owner on 15 October 2026. Empty lists succeed.
Reads compute exact `running`/`unfinished` status without writes, freshness or
pruning. Writers retain the newest 1,000 entries per repository plus a separate
1,000 globals, protecting live invocations and independent provenance evidence.
See the [activity guide](activity.md#ordered-history-and-bounded-retention).

`mycel ingest [--repo <name> | --all] [--embed] [--confirm-empty]` accepts repeated literal repository selectors, organization scope or the current directory. Each selected repository gets a complete disk, local-branch and stash capture, identity/dependency publication, mechanical detection and unlocated-version collection. Git reads preserve the checkout and local metadata. Incomplete capture refuses before any deletion; an unexpected empty corpus needs explicit `--confirm-empty`. Required source guards are acquired without waiting. Busy affected owners remain visible as `dependencyPending`, `stalePending` or `collectionPending` and return exit 1 until a later pass completes the work. A pass publishes the capture it read (MYC-1.37): a file that changes after the capture, or a branch or stash that appears, disappears or moves meanwhile, does not stop the pass; the reply names it under `changedDuringPass`, the status stays 0, and the next pass takes it up. Another repository's disk is never compared with its index during a pass; that repository's own pass does it. A PostgreSQL fault behind `store_unavailable` names the error class and SQLSTATE, never the server's text.

The reply contains a `repositories` object with `ran`, `changed`, file/chunk/decision counters, current `stale`, current-model version `pending`, embedding part coverage and dependency/detection/collection counts. Counts include actual foreign ownership changes and accumulate across the invocation. Numbered Builds record those exact counts with readable identity decisions. Unchanged passes retain feature/audit rows. `--embed` starts scoped embedding after publication guards close; ordinary ingest uses only local coverage planning. An interruption exits 2. A failure after acknowledged commits preserves the repository results and adds `countsState: "committed_prefix"`, a closed error and `stopped`. The [reconciliation guide](reconciliation.md#complete-public-ingest) describes guards, corpus ownership and retry behavior.

`mycel read <place>` or `mycel read --id <search-result-id>` returns schema-1
indexed chunk text with canonical qualified address and complete freshness
metadata. It accepts one optional `--repo`, `--no-fresh`, and `--context 0..50`.
The [reading guide](reading.md) describes exact selection, generated chunks,
ambiguity candidates and the 5 MiB UTF-8 cut limit. `info` adds `commands` and
`readReply: 1` and `searchReply: 3`; no separate capabilities command exists.

`mycel overview [--repo <name>] [--dir <relative directory>]` prints stored
index-only directory sections with exact file/symbol counts and complete text.
It takes one enabled repository, runs no pass, writes nothing and returns an
empty `sections` list normally for a valid absent directory. `.` names the code
root; absolute and escaping directories are `invalid_input`. Overview sections
embed as documents, compete only in their own repository, and never bridge to
code. The [overview guide](overview.md) describes ordering, omitted counts,
atomic pass reconciliation and stable vectors on body-only edits.

## Recovering Origin Links

`mycel recovery [<chunk>] [--repo <name>] [--path <path>] [--k <pairs>] [--dry-run] [--review]`
selects unlinked current chunks, gathers local document/test/history/snapshot
and existing-vector candidates and applies the separate Origin judgement.
It reads the indexed snapshot and calling clone without ingesting, embedding
or reading a remote. `--dry-run` has no model credential, call or state write.
`--review` instead selects existing inferred/recovered links and calls the
configured independent reviewer to update their scores/bands or withdraw an
unrelated proposal. A model result creates no verification or authoritative
source dependency. The [recovery guide](recovery.md) gives source availability,
exact evidence, reply fields, score caps and finite execution guards.

<!-- command-contract:start -->
```json
{
  "help": {
    "program": "mycel",
    "version": "2.0.0",
    "usage": "mycel <command> [arguments]",
    "commands": [
      {
        "name": "search",
        "description": "Search by meaning or exact wording",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--k <count>",
          "--only code|docs",
          "--no-fresh"
        ]
      },
      {
        "name": "ingest",
        "description": "Bring repository knowledge up to date",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--all",
          "--embed",
          "--confirm-empty"
        ]
      },
      {
        "name": "embed",
        "description": "Embed pending chunk text",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--all",
          "--dry-run",
          "--retry-failed"
        ]
      },
      {
        "name": "status",
        "description": "Report repository counts",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--all"
        ]
      },
      {
        "name": "repos",
        "description": "List repositories or remove indexed rows",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help"
        ]
      },
      {
        "name": "stale",
        "description": "Report stale chunks",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>"
        ]
      },
      {
        "name": "refs",
        "description": "Report retained source references and faults",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--unresolved"
        ]
      },
      {
        "name": "derive",
        "description": "Assert a dependency",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--remove"
        ]
      },
      {
        "name": "confirm",
        "description": "Record verification",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--by <name>",
          "--how read|check"
        ]
      },
      {
        "name": "justify",
        "description": "State an Origin Link and record verification",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--by <name>",
          "--file <pairs.jsonl>"
        ]
      },
      {
        "name": "origins",
        "description": "Report Origin Links and coverage",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--missing",
          "--path <path>",
          "--changes",
          "--unresting",
          "--no-fresh",
          "--needs-nothing <requirement>",
          "--reason <text>",
          "--clear-needs-nothing <requirement>"
        ]
      },
      {
        "name": "recovery",
        "description": "Recover inferred Origin Links from local evidence",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--path <path>",
          "--k <pairs>",
          "--dry-run",
          "--review"
        ]
      },
      {
        "name": "drifts",
        "description": "Report dependency review work",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--closed",
          "--all-versions"
        ]
      },
      {
        "name": "relate",
        "description": "Assert a relation",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--remove"
        ]
      },
      {
        "name": "verifications",
        "description": "Report verification records",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--history"
        ]
      },
      {
        "name": "classify",
        "description": "Explicitly classify dependency review work",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--all",
          "--k <count>",
          "--dry-run"
        ]
      },
      {
        "name": "summaries",
        "description": "Report, build, regenerate or remove summaries",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--dry-run"
        ]
      },
      {
        "name": "overview",
        "description": "Read the stored code overview",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--dir <directory>"
        ]
      },
      {
        "name": "grep",
        "description": "Run grep with a related search tail",
        "available": true,
        "rawArguments": true,
        "options": []
      },
      {
        "name": "read",
        "description": "Read one exact chunk",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--id <id>",
          "--context <lines>",
          "--no-fresh"
        ]
      },
      {
        "name": "undocumented",
        "description": "List code that no document section describes",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--path <path>",
          "--no-fresh"
        ]
      },
      {
        "name": "activity",
        "description": "Report recorded work",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--all",
          "--entry <id>",
          "--kind <kind>",
          "--k <count>"
        ]
      },
      {
        "name": "evaluate",
        "description": "Explicitly evaluate retrieval or dependency review",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "--repo <name>",
          "--kind retrieval|drift",
          "--live"
        ]
      },
      {
        "name": "init",
        "description": "Initialize the private index store",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help"
        ]
      },
      {
        "name": "api-key",
        "description": "Store a Voyage or Jev API key in the login Keychain",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help",
          "voyage|jev"
        ]
      },
      {
        "name": "info",
        "description": "Report program and configuration diagnostics",
        "available": true,
        "rawArguments": false,
        "options": [
          "-h",
          "--help"
        ]
      }
    ],
    "options": [
      "-h",
      "--help",
      "--repo <name> (repeatable where supported)",
      "--all (where supported)"
    ],
    "buildSelection": "Installed launcher: -v <number> must be first",
    "stage": "CLI foundation, strict settings and diagnostics, repository listing and atomic removal, complete repository status, complete scoped ingest, read-only ordered activity history and exact entry details, retained reference reporting, guarded dependency and relation assertions, exact verification and read-only history, atomic stated justification and on-demand Origin Coverage, exact indexed chunk reading, evidence-bearing search, scoped embedding, atomic summary builds, summary regeneration and removal, read-only summary status and dry-runs, finite classification and guarded Origin recovery, local provenance reports, and private store initialization; system grep preserves its output and can append a read-only related search tail"
  },
  "errors": [
    "invalid_input",
    "io",
    "settings",
    "unknown_repository",
    "store_unavailable",
    "store_format",
    "busy",
    "refused",
    "internal"
  ],
  "exitStatuses": {
    "done": 0,
    "failed": 1,
    "stopped": 2
  }
}
```
<!-- command-contract:end -->

## Read-only one-time replacement planning

The [Mycel-owned replacement procedure](replacement.md) documents exact current
inventory, independently inspectable ownership evidence, a qualified new
launcher/private store, verified command cutover and restrictive exact cleanup.
`python -m mycel_build replacement-plan --inventory /absolute/inventory.json`
only reads explicit evidence and emits instructions. `replacement-validate`
takes `--plan`, `--plan-sha256` and `--report` and only verifies the bound ordered
operator observations. Neither command edits shell files, executes cleanup,
opens a database or copies version1 index state. Uncertain ownership stays
blocked; source/document corpora and unrelated objects are preserved.

A report binds observations; it does not authenticate ownership, exhaustive
inventory, actual PostgreSQL execution or native Build qualification. Retain
and independently review the operator receipts. The procedure includes the
qualified-release binding, a concrete inventory/report worksheet, explicit new
private-store commands and absent-old-runtime handling. Unit finite-catalog
proofs and separately scoped disposable PostgreSQL rehearsals retain their
own evidence; neither performs owner replacement. The installed command is
`~/.local/bin/mycel`; callers use `mycel grep` in place of `better-grep`.

<!-- sources:
mycel:@code/src/mycel_build/_replacement.py#replacement_plan
mycel:@code/src/mycel_build/_replacement.py#validate_replacement_report
mycel:@code/tests/test_replacement.py#ReplacementTests
-->
