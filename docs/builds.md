# Staging and maintaining offline Mycel Builds

The development tool runs as `python -m mycel_build` from this repository's
source tree. It installs no second product command. Creation requires the
accepted ordinary CPython **3.14.7** development pin; the repository's existing
3.14.8 developer environment remains useful for fixture tests but is refused
for creation. The tool uses the standard library and has no development
package dependencies or runtime installer.

Mycel supports Apple Silicon Macs only (`macos-arm64`).
`packaging/build-lock.json` fixes the exact CPython 3.14.7
python-build-standalone 20260901 `install_only_stripped` archive for that target,
all 29 direct/transitive dependency versions, their wheel filenames/hashes and
the bundled licence hashes. The required system is macOS 14 or later.
Mycel's tokenizer JSON, source metadata, licence,
parser grammar extension modules and other packaged data are retained.

The development commands return one JSON result, including invalid arguments
and partial failure. With the pinned interpreter selected and `src` on its
development import path:

```sh
PYTHONPATH=src python -B -m mycel_build --help
PYTHONPATH=src python -B -m mycel_build prepare --target macos-arm64 --assets /tmp/mycel-assets
PYTHONPATH=src python -B -m mycel_build create --target macos-arm64 --assets /tmp/mycel-assets --registry /tmp/mycel-build-fixtures
PYTHONPATH=src python -B -m mycel_build create --target macos-arm64 --assets /tmp/mycel-assets --registry /tmp/mycel-build-fixtures --store-settings /path/to/explicit-config.toml
PYTHONPATH=src python -B -m mycel_build list --registry /tmp/mycel-build-fixtures
PYTHONPATH=src python -B -m mycel_build verify-source 1 --registry /tmp/mycel-build-fixtures
PYTHONPATH=src python -B -m mycel_build install-launcher --bundle /tmp/mycel-build-fixtures/1/launcher-bundle --home /tmp/mycel-fixture-home
PYTHONPATH=src python -B -m mycel_build withdraw 1 --reason "parser regression" --registry /tmp/mycel-build-fixtures
PYTHONPATH=src python -B -m mycel_build prune 1 --registry /tmp/mycel-build-fixtures
```

Only explicit `prepare` downloads public pinned archives/wheels and verifies
their hashes. `create` makes private read-only copies of verified local assets
and checks those copied bytes before installation, so later changes in the
asset cache cannot change the installed inputs. Installation uses
noneditable wheels, verifies every wheel RECORD member, rejects import hooks,
bytecode, special files, path escapes and collisions, and invokes no package
resolver or installer. Runtime archive structure and each complete wheel RECORD
are validated before installation writes begin. Filesystem collision checks
include macOS case folding and Unicode normalization. A product-only wheel
contains `mycel`, its declared package metadata and data; it excludes
`mycel_build`, excludes the source-development marker, and refuses a
source-provided Build number.

The frozen source-input map excludes development egg-info metadata, bytecode
and tool caches. Changing those generated files cannot change a Build's source
identity; changing product source, checks, packaging inputs or guides does.
The check-input digest covers the runner scripts, all imported source modules,
test and claim declarations, `Makefile` and package metadata. A test-only digest
cannot establish that the gate itself has retained its recorded semantics.

After successful native probes, creation runs every declared `unit` and `store`
check using the sealed installed product and its bundled `-I -B` interpreter.
It reconstructs the captured tests, builder fixtures, guides and declarations
in a private disposable workspace. That workspace's `src/mycel` is a link to
the installed package; parent and subprocess fixture imports therefore load
installed bytes, while source-reading architecture checks can inspect them.
The actual source checkout and developer runtime are unreadable in an
operating-system sandbox. Every loaded parent product module is verified to
resolve inside the installed program, and the installed manifest is checked
again afterward. The gate uses a private relocated program copy whose full
manifest equals the retained stage before and after execution. This keeps the
owner registry unreadable even when the stage uses the ordinary default registry.

`--store-settings` selects an explicit settings file from which the builder
reads only the password-free `store.address`. The installed native backend
opens its administrative database and generated `mycel_check_` databases;
it never opens the address's owner database. Ordinary fixed store Keychain
authentication remains available. Owner settings are unreadable and the owner
home is unwritable inside the check boundary. No selected settings contents,
address, credentials, exception traceback, provider body or raw check streams
are retained. Check names, kinds, requirement IDs, status and closed generic
failure descriptions are retained with their exact frozen source identity.
`eval` and `live` checks remain excluded.

The default check bootstrap uses the installed SQL schema initializer to seed
empty disposable fixture tables. It creates no user-operation audit entry.
The dedicated initialization/activity checks select an uninitialized disposable
database and exercise the actual installed command and its numbered audit.

The sandbox denies inbound network traffic and restricts outbound traffic to
the configured loopback PostgreSQL port. Unreachable-target fixtures may bind
an unused loopback TCP port without accepting connections. macOS's
network-address grammar cannot constrain a non-loopback server
hostname or IP, so such a server currently produces an explicit unavailable
automatic gate. With no `--store-settings`, all unit checks still run and
each required store check records its missing-backend failure. Neither case can
count as passing automatic checks. Fixture failures and incomplete processes
produce a failed staged record; no named check is skipped to make the gate pass.

`verify-source` compares the current frozen source map, Git identity and lock
with one staged record. It validates the retained source/check manifests and
their recorded digests, then reports exact added, removed and changed paths.
It returns status 0 only for a complete match, and status 1 for stale or
incomplete evidence; earlier stages that bound only tests/checks report
`completeCheckInputs: false`. The command takes a nonwaiting shared registry
lock and writes no files. A match establishes source binding only: it does not
rerun native probes, validate installed file integrity, execute the automatic
gate or make a Build working. Retained check evidence remains specific to the source
identity recorded when that stage ran.

The default registry is `~/.mycel/builds`. Acceptance fixtures use explicitly
private temporary registries and allocate no owner numbers. A short nonwaiting
operating-system maintenance lock serializes durable lowercase hexadecimal
allocation. The fsynced allocation journal reserves a number before packaging;
an interrupted initial record is recovered as failed without reuse. Every
record retains `build.json`, `checks.json`, a fixed sanitized `build.log`, and
the pre-created read-only `run.lock`. Listing takes a nonwaiting shared registry
lock and treats a damaged record as unavailable without disrupting other
records or later number allocation. Retained records for unsupported historical
targets remain readable in listings with `targetSupported: false`; current
Build operations refuse those targets and leave their recorded files unchanged.
Recovery only reconstructs a missing or
partial initial allocation whose retained files still match the initial
record, empty checks, allocation log and empty lock. Damaged, unsafe, staged,
terminal and pruned records retain their existing bytes and reserved numbers;
they are never rewritten as interrupted initial allocations. Failed/pruned
identities remain accounted for.

Each staged record retains source commit/dirty identity, exact source-input
digests including test/gate scripts and guides, runtime/archive and dependency
pins, lock digest, product wheel digest/version, supported store format **2**,
search-reply version **3**, check-input digest, data/licence-file digests and a
complete immutable installed-file manifest. The manifest covers regular files,
contained relative symlinks, directory permissions and the program root.
Absolute links, missing targets and link cycles are refused. Staging writes the
allocated numeric Build identity into `mycel/data/build-identity.json` after
wheel installation; that file is sealed and covered by the same manifest.
Development source carries no Build number. Installed program files/directories
lose their write bits before the manifest is recorded;
changed bytes, paths or modes invalidate integrity.

Installed execution is exactly the bundled
`runtime/bin/python3 -I -B -m mycel.cli` with the supplied arguments. It keeps
the caller's directory and environment, including `MYCEL_CONFIG`, and replaces
the process through `execv`; no installed invocation extracts assets or runs
an installer. The independent launcher acquires the selected Build's shared
read-only lifetime run lock before replacing itself with that command.

On a matching native host, the initial stage probes two different private
installation paths. An operating-system sandbox denies reading the source
checkout and developer directory, network access and file writes. An additional
Python audit hook denies mutation/network calls in the native/data probe. It
verifies interpreter isolation, ordinary non-free-threaded 3.14.7 identity,
versions/closure and module locations for every locked dependency, imports
product-used modules, and checks local grammar parsing, exact tokenizer data
and the allocated immutable Build identity. Direct `--help` and
`info` must return their actual JSON replies with status 0
and empty standard error against private missing/invalid settings. Installed
and caller file manifests are checked afterward; owner settings/stores are
never inspected. No paid provider operation runs.

The optional, unused Hugging Face transport dependency `hf_xet` is checked by
dynamic-link loading and its Python-init symbol only. Importing its Python
extension in pinned 1.7.0 initializes cache logging; Mycel's local tokenizer
does not import that transport. This probe does not claim its transport API or
module initialization is write-free. Product-used native extensions are
actually imported and exercised. No special HF environment controls are added
to ordinary installed execution or these final probes.

Pure transitive packages used by remote Hugging Face APIs are checked by their
locked versions, dependency closure and installed module locations. Their
unrelated module initialization is not a write-free product-operation claim:
the pinned `filelock` imports perform temporary link-capability probes. The
Build evidence separately lists the dependency module origins and the modules
actually imported during the native/data probe.

Creation runs the native product and independent launcher bootstrap probes,
the complete installed unit/store suite, and the packaged selector/CLI checks
from two private installation paths. The receiver derives its expected named
inventory and ordered claim lists independently from the frozen source; a
child cannot define its own expected count or substitute a partial report.
The retained report names every outcome and preserves all 333 requirement rows,
including pending requirements. Evaluation and live checks are never selected
by this automatic gate and their pending rows are not promoted.

An unavailable required probe or failed check produces `failed` and retains its
sanitized name and reason. If the suite passes but active unit/store requirements
still lack passing named proofs, `automatic_requirement_proof_gate` records their
exact IDs and blocks qualification. `automaticQualification` becomes true only
when all required groups and all active automatic requirement proofs pass; its
certificate binds the exact Build, source/check inputs, installed manifests and
results. Pending eval/live rows remain separate on-demand work.

**The internal staging seam never publishes `working`**. The prepared development
release continuation described below owns final atomic publication; Mycel1
replacement remains separate. Private working records used by
the relocation checks exist only in disposable probe homes, never in the owner's
published registry. The packaged checks measure actual elapsed times and record
the target/runtime; they claim no unmeasured startup threshold.


## Installing the independent launcher

Creation also stages and checks `launcher-bundle` beside the Build's program.
Its own ordinary CPython bootstrap uses the recorded runtime archive pin,
licenses and a standalone selector that imports only the standard library.
It is independent of the selected Build, the source checkout and the developer
interpreter. Both program trees have immutable complete manifests. Creation
records the bootstrap's two-path offline probe; an unavailable or failed probe
prevents a successful stage.

`install-launcher --bundle <verified-bundle>` first validates and copies that
complete bundle under `~/.mycel/launcher/`. It then atomically changes
`~/.local/bin/mycel` to a verified owned bundle entry. An unrelated file or
uncertain symlink is refused. Older installed bundles remain; neither invocation
nor maintenance performs launcher-bundle cleanup. The internal `--home` option
allows a separate fixture home; the examples above use private paths. Normal
launcher execution uses the caller's home for its `~/.mycel/builds` registry.

Installation returns one JSON result. A failure before entrypoint replacement
keeps the previous entrypoint. A failure or interruption after a completed
replacement reports the actual installed state as a partial outcome; it does
not pretend the old link remains. No installation initializes a store or changes
settings. No invocation installs, extracts or updates its bootstrap.

## Choosing and running a Build

With no prefix, `mycel` selects the highest numeric intact compatible working
Build: `10` follows `f`. `mycel -v f info` explicitly selects `f`; `-v` has this
meaning only as the first argument. Later arguments, including grep options,
are passed exactly to the chosen program. A withdrawn Build can run only when
explicitly named, with its recorded reason on standard error. Unknown or
malformed numbers return `invalid_input`; known building, failed, pruned,
damaged or incompatible Builds return `refused`. No available default returns
`refused`. Errors list the intact runnable numbers in numeric order.

Selection reads distribution files under a nonwaiting shared registry lock and
holds it until the chosen Build's pre-created `run.lock` is shared-locked. The
read-only descriptor survives process replacement for the invocation's lifetime.
The launcher preserves arguments, directory, process identity, standard streams,
signals and final status. It consults no settings or database, and listing and
invocation write no cache or access log. A maintenance conflict returns `busy`.

## Withdrawal, pruning and rollback

`withdraw <build> --reason <text>` changes only an unpruned working Build to
withdrawn under the exclusive nonwaiting registry lock. The nonempty reason is
retained. The next default selection falls back to the preceding intact working
Build; a process already running keeps its selected Build. A late write failure
or interruption reports the actual persisted record as a partial outcome.

`prune <build>` accepts one specifically named failed or withdrawn Build. A
working Build must first be withdrawn. Pruning takes the registry maintenance
lock and a nonwaiting exclusive lock on its retained `run.lock`; a selected or
running Build returns `busy` before deletion. It removes only that Build's
`program` and recorded `launcher-bundle/program` trees. Its record, checks, log,
run lock and launcher-bundle metadata remain, as do every independently installed
bootstrap bundle and every other Build. There is no age, space or automatic
pruning rule.

A pruning record becomes unavailable through `prunedAt` before removal starts.
`pruneComplete` records whether all program cleanup finished. Interrupted cleanup
reports the actual partial record; an explicit retry names the same Build and
preserves its original pruning time. Unsafe program paths are refused, and
symlinks inside program trees are removed without following their targets.

Installation, selection and maintenance change no settings or store structure.
Selecting an older compatible Build can reuse its supported store; selecting
an older incompatible executable does not downgrade a database. That executable
refuses the newer format while `info` remains diagnostic and grep retains its
specified fallback. Structure changes belong only to explicit `mycel init`.
Use an owner-restored compatible database or a compatible newer Build for
rollback after a migration; no command performs a reverse migration.

<!-- sources:
mycel:@code/src/mycel_build/_launcher.py#stage_launcher
mycel:@code/src/mycel_build/_launcher.py#install_launcher
mycel:@code/src/mycel_build/_launcher_runtime.py#select_build
mycel:@code/src/mycel_build/_launcher_runtime.py#main
mycel:@code/src/mycel_build/_maintenance.py#withdraw
mycel:@code/src/mycel_build/_maintenance.py#prune
mycel:@code/src/mycel_build/_registry.py#run_guard
-->

Primary contracts: [runtime release](https://github.com/astral-sh/python-build-standalone/releases/tag/20260901),
[Python isolation flags](https://docs.python.org/3.14/using/cmdline.html),
[wheel format and RECORD](https://packaging.python.org/en/latest/specifications/binary-distribution-format/).

## Selective working-publication preparation

Internal `create_stage` stays staging-only. Development `create` continues via
`create_release` only when the complete current native, bootstrap, automatic
and packaged checks and every active automatic requirement proof pass. It
recaptures the exact source, requires a separate private credential group, and
revalidates all checked inputs under the nonwaiting registry maintenance lock.
The current strict frozen inventory, full332 proof map, queued cancellation,
and exact16 ordered packaged cases at each of two relocations remain required.

Publication writes final checks and the sanitized log before atomically
replacing the working record last. Earlier failure or interruption leaves the
old numeric default available. A failure after that final replacement reports
the actual working record as partial; it cannot downgrade a committed record.
No owner launcher installation, replacement or cleanup is part of creation.

The private credential check now uses a fresh copy of a licensed, pinned public
Apple regression Keychain. A build-only Python helper opens a nonnull explicit
native handle and validates its current private path before unlock, lookup or
lock. The current staged program's actual `Credentials.embedding_key` consumes
the supported literal `embedding.key_command` output privately. No compiler,
provider, database, item creation/deletion, default or search-list setter is
used. Native buffers are zeroed/freed; Python strings do not promise secure
erasure. The private copy is removed only after current child groups are gone.

Preference equality describes only the probe profile's observed view. It is
not an exhaustive owner-preference or daemon-isolation proof, and this override
check does not exercise the default login-item reader. An unavailable API,
fixture-format incompatibility, scope/cleanup failure, cancellation or unknown
launch refuses working publication. No protected-entropy or owner-state repair
is attempted. Apple source and license are frozen offline inputs under
`packaging/native-fixtures/apple-security`; the installed wheel remains
product-only.

A separate accepted-program feasibility diagnostic informed this implementation.
Every new Build must execute its own current-source/current-program check; the
diagnostic cannot be replayed as qualification. Unit fixtures use openly
fictional complete328-automatic/333-registry preconditions and fake native APIs
to test policy. No new source application, automatic Build qualification,
provider qualification or working release is claimed by this preparation; all315
previous shared ordered claim lists remain unchanged.

<!-- sources:
mycel:@code/src/mycel_build/_release.py#create_release
mycel:@code/src/mycel_build/_publication.py#publish
mycel:@code/src/mycel_build/_keychain_probe.py#probe_private_keychain
mycel:@code/src/mycel_build/_credential_fixture_reader.py#read_fixture
mycel:@code/src/mycel_build/_credential_probe_client.py#main
mycel:@code/src/mycel_build/_credential_contract.py#credential_probe_passed
mycel:@code/src/mycel_build/_qualification.py#qualification_certificate
mycel:@code/tests/test_working_publication.py#WorkingPublicationTests
-->

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
inventory, actual PostgreSQL execution or native Build qualification. Actual
operator evidence and independent review remain required. Disposable-file and
finite-catalog unit rehearsals are not an owner replacement. No such operation
or new acceptance occurred in this source preparation.

<!-- sources:
mycel:@code/src/mycel_build/_replacement.py#replacement_plan
mycel:@code/src/mycel_build/_replacement.py#validate_replacement_report
mycel:@code/tests/test_replacement.py#ReplacementTests
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
