# Distribution lock and licences

`build-lock.json` is the reviewed release input for the supported Apple Silicon
macOS target (`macos-arm64`). Its runtime SHA-256 matches MYC-15 and the public GitHub release API.
Every dependency uses an exact noneditable PyPI wheel, including the complete
29-package dependency closure of the repository's direct pins on CPython 3.14.
Each entry retains its public source URL and SHA-256.

`licenses/` contains licence/notice bytes copied from those exact wheel and
runtime archives. The tokenizers 0.23.2 wheel omits a licence file, so its
Apache-2.0 text is retained from the upstream v0.23.2 LICENSE with its source URL
and digest. Files shared by the retained archives are stored once. The
stager verifies every checked-in licence against the lock before use and
bundles these files alongside the runtime's original notices.

Development creation is pinned to ordinary CPython 3.14.7 and uses standard
library wheel-writing, archive and registry code only. It does not use the
system Python, Node, a dependency resolver, editable installs or a build backend
at installed execution time. Preparation may explicitly download public pinned
inputs; staging and installed probes remain offline. Read `docs/builds.md` for
the partial staging interface and the later working-publication boundary.

Installation uses private read-only copies whose bytes are checked against the
lock. It preflights the whole runtime archive structure and wheel RECORDs before
writing members, and refuses special files, bytecode and import hooks, escaping
or absolute links, link cycles, and path collisions under supported macOS
filesystem case/Unicode rules. An allocated numeric Build identity is added only
to the installed product data and retained in its immutable manifest; the
development wheel refuses any source-supplied Build identity.

The repository build also produces a separately sealed `launcher-bundle` with
its own copy of the exact pinned bootstrap runtime and licenses. The installed
selector is standard-library-only and runs with `-I -B`; it chooses Builds
without importing the product or reading settings/store state. Launcher
installation stages a verified complete bundle before atomically changing its
owned entrypoint and keeps older installed bundles. See `docs/builds.md` for
selection, withdrawal, explicit program-only pruning and rollback.

## Selective working-publication preparation

Internal `create_stage` stays staging-only. Development `create` continues via
`create_release` only when the complete current native, bootstrap, automatic
and packaged checks and every active automatic requirement proof pass. It
recaptures the exact source, requires a separate private credential group, and
revalidates all checked inputs under the nonwaiting registry maintenance lock.
The complete frozen inventory, including inherited test methods, its ordered proof
map, queued cancellation and sixteen ordered packaged cases at each of two
relocations remain required. The installed gate uses the shared bounded worker
runner and acknowledged database recovery; it does not substitute a development
report for installed execution. Requirement rows retain actual chapter status,
and draft status waives no automatic proof.

Publication writes final checks and the sanitized log before atomically
replacing the working record last. Earlier failure or interruption leaves the
old numeric default available. A failure after that final replacement reports
the actual working record as partial; it cannot downgrade a committed record.
No owner launcher installation, replacement or cleanup is part of creation.

The private credential check uses a fresh copy of a licensed, pinned public Apple
regression Keychain. Its Python helper validates a nonnull explicit native handle
and private path before unlock, lookup or lock. The staged program consumes the
supported `embedding.key_command` output privately. No item creation/deletion,
default/search-list setter, compiler, provider or database is used by this probe.
Preference equality describes the probe profile's observed view; it is not an
exhaustive owner-preference or default login-item-reader proof. The current
Build must pass this check and its cleanup; old diagnostic results cannot qualify
it. Synthetic complete proof maps test publication policy, while real installed
results are required for each working record. Owner launcher installation and
replacement remain separate.

<!-- sources:
mycel:@code/src/mycel_build/_release.py#create_release
mycel:@code/src/mycel_build/_publication.py#publish
mycel:@code/src/mycel_build/_keychain_probe.py#probe_private_keychain
mycel:@code/src/mycel_build/_qualification.py#qualification_certificate
mycel:@code/tests/test_working_publication.py#WorkingPublicationTests
-->

## Read-only one-time replacement planning

The [Mycel-owned replacement procedure](../docs/replacement.md) documents exact current
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
