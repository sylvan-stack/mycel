# Settings

Mycel reads one UTF-8 TOML file for each command invocation: `~/.mycel/config.toml`, or the file named by `MYCEL_CONFIG`. It holds an immutable snapshot for that operation and never creates, rewrites or copies the file into a database. Help works without settings. The only Mycel environment variables are `MYCEL_CONFIG` and `MYCEL_GREP_PLAIN`; old model, repository, database and provider overrides have no effect.

Except for `info` and `grep`, a command requires valid settings and a store address before its handler runs. An unknown table or key, invalid TOML, wrong type, out-of-range number, unsupported model/dimension pair or incomplete reviewer configuration produces one `settings` error. Diagnostics identify the file, every unknown qualified key and its line when available, and either accepted keys or an unambiguous correction. They never include the supplied values. A misspelling is never silently fixed.

`mycel info` reports the package version, settings file and settings diagnostics, including missing or invalid settings. With valid settings it also reports the store's state, format, dimensions, generation and exact password-free location; unavailable and incompatible stores remain successful diagnostic replies. It includes the running numbered Build when installed and the configured model/reviewer metadata without resolving model credentials. `mycel grep` runs the first grep on PATH with literal arguments and inherited input/output before optional tail settings are loaded. Eligible invocations can append the normal read-only related search; invalid settings suppress that tail with one diagnostic line and preserve grep's status. `MYCEL_GREP_PLAIN=1` requests grep alone without loading tail settings. No JSON is added to grep's output; see the [grep guide](command-line.md#grep-and-its-related-search-tail).

<!-- sources:
mycel:@code/src/mycel/_cli.py#_plain_grep
mycel:@code/src/mycel/_grep.py#append_tail
mycel:@code/src/mycel/_grep.py#search_tail
-->

Settings diagnostics have this contract. `readable` is false for a missing, unreadable, non-UTF-8 or malformed TOML file; it remains true for a parseable file with validation faults. A fault always has a message and may have a key and line. Reports never dump settings values.

<!-- settings-contract:start -->
```json
{
  "reportFields": ["file", "exists", "readable", "unknownKeys", "faults"],
  "faultFields": ["message", "key", "line"],
  "environment": ["MYCEL_CONFIG", "MYCEL_GREP_PLAIN"],
  "embeddingModels": {"voyage-code-4": [256, 512, 1024, 2048]}
}
```
<!-- settings-contract:end -->

## Tables and defaults

All tables are optional; `store.address` is required for commands other than `info` and `grep`. Integers exclude booleans. Numeric limits are finite. Tables accept only the keys below, including nested tables and shared-document entries.

| Table | Keys and defaults |
| -- | -- |
| `store` | `address`: password-free PostgreSQL URI naming a host, user and database; optional port; no default. Only `sslmode` and `connect_timeout` URI query options are supported. Passwords and alternate credential sources such as `passfile` or `service` are rejected. A password challenge uses only the private Keychain reader below; the store connection/init task remains in progress. |
| `embedding` | `model = "voyage-code-4"`; `dimensions = 1024`; `attempts = 5` (integer ≥ 1); optional `key_command` (list of texts). The packaged initial catalog accepts only voyage-code-4 with 256, 512, 1024 or 2048 dimensions. Its verified offline tokenizer and complete-input planning are described in [embedding](embedding.md). |
| `scan` | `document_endings = [".md"]`; `code_endings` and `skip_folders` use the accepted legacy lists. All three are lists of texts. |
| `search` | `freshness_seconds = 5` (finite number > 0); `shared_documents` is a list of tables containing only nonempty `repo` and relative `paths`. The owner-decided defaults select `mycel` with `.` and `arbol` with `GLOSSARY.md`. An empty list disables sharing. |
| `drifts` | `debounce_seconds = 300` (integer ≥ 0); `model = "jev-1.13.0"` (exact `jev-major.minor.patch`); `confidence_floor = 0.7` (finite 0–1); `candidates = 100`, `at_once = 2`, `attempts = 2`, `max_input_bytes = 24000`, `review_max_input_bytes = 1048576` (integers ≥ 1); `seconds = 300`, `jev_timeout_seconds = 10`, `review_timeout_seconds = 120` (finite numbers > 0); optional reviewer fields below. |
| `summaries` | `at_once = 4` (integer ≥ 1); optional `command` (list of texts) and `instructions` (absolute/home folder). Without a command, no summary writer is configured. |
| `organizations.<name>` | Required absolute/home `root`; optional `artifact_root`, defaulting to `~/Artifacts/<last part of root>`. |
| `repos.<name>` | `enabled = false`; optional `code_root`, `artifact_root` (absolute/home folders), `code_subdirs` (relative paths, absent/empty means whole code root), `evaluation` (relative path under the artifact root), `test_patterns`, `generated_patterns` (lists of texts, with the accepted legacy defaults). `repos` reports resolved folders, their provenance and per-repository faults. |

Folder `~` and initial `~/` mean the invocation's home folder. Other folder paths must be absolute. Relative paths may not be absolute, begin with `~`, contain NUL or traverse a parent. The settings validator does not inspect repository membership or resolve symlinks; the scope layer handles physical containment before file access.

The packaged default data preserves the fifteen legacy code endings, the legacy code skip list and test/generated path patterns. Named shared-document and folder selections are applied uniformly as settings data. They create no repository, select no fallback repository, and trigger no product-specific procedure; sharing later uses only enabled configured repositories. The accepted default selections still contain product names; the broader literal name prohibition in MYC-0.3/MYC-1.5 needs specification reconciliation before claiming final conformance.

A fictional settings file:

```toml
[store]
address = "postgresql://check@localhost:5432/fixture"

[embedding]
model = "voyage-code-4"
dimensions = 1024

[search]
shared_documents = [{ repo = "handbook", paths = ["."] }]

[organizations.Orchard]
root = "~/repos/orchard"

[repos.cellar]
enabled = true
code_root = "~/repos/cellar"
artifact_root = "~/Artifacts/cellar"
code_subdirs = ["src", "tests"]
evaluation = "evaluation/search.toml"

[repos.handbook]
enabled = true
artifact_root = "~/Artifacts/handbook"
```

## Private credentials

Credential acquisition is lazy and attempted at most once per invocation for
each purpose, including unavailable results. The internal reader uses fixed
`/usr/bin/security` and the home login Keychain. Generic passwords use service
`mycel` with accounts `voyage-api-key`, `store-password` and `jev-api-key`.
Compatible editors create/replace the same items and explicitly trust
`/usr/bin/security` for reading; credential readers never rewrite their access rules.

Use `mycel api-key voyage` or `mycel api-key jev` to set either API key. With valid settings, the command reads one nonempty printable-ASCII key from a controlling terminal without echo and writes its named login-Keychain item. It returns only the provider, service/account identity and `replaced` flag. There is no secret argument, stdin fallback, settings change, store connection or provider call. An unavailable terminal or unsafe/empty input returns `invalid_input`; a failed native write returns `refused`. Native Keychain permission can be required when replacing access rules, and a failed access-rule update may follow a successful secret update.

The writer passes one bounded hexadecimal-data command to `/usr/bin/security -q -i` over a private pipe, with `/usr/bin/security` explicitly trusted for reading. It never places the secret in OS argv, child environments, output, logs or plaintext files. Only duplicate-item status selects one replacement attempt; no previous secret is read. The store-password item is outside this command's scope.

If `embedding.key_command` is configured, it supplies the embedding key instead
of the Keychain. The executable is resolved once; its argv is literal and no
shell runs. Only the final line break is removed from successful UTF-8 output.
Nonzero status, unavailable execution, timeout, excessive output or invalid
output means no key. Raw output and process diagnostics are private.

Jev access requires explicit classification or live drift qualification.
Ordinary ingest/search/reporting and dry-runs acquire none. Reviewer commands
own their separate authentication and receive none of Mycel's credentials.
The store target retains the specified password-free location for diagnostics,
and passwords are consumed only by an in-process connection boundary. Credentials
and store addresses are never forwarded to child programs.

The store connection first tries without a password and reads its Keychain item
only after a server password challenge. Acquisition shares the connection's
remaining deadline, bounded further by the credential reader's own limit.

## Protocol-1 reviewer setup

Supply `review_command`, `review_provider`, `review_model` and `review_revision` together, or omit all four. Omission is valid and leaves uncertain work pending for the later classifier. Provider/model identify the actual pinned deployment; moving aliases are not a supported deployment identity. Mycel rejects obvious moving aliases locally; the adapter and later qualification validate actual identities.

The command is nonempty argv, each member nonempty and NUL-free. Its first member is an absolute path or starts `~/`; only that first member receives leading-tilde expansion. Every later argument remains literal, including spaces, dollar signs and tildes. The revision matches `[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}`. Settings validation does not launch or probe the command, including in a dry-run.

These values are fictional. Install and authenticate an independent protocol-1 adapter separately and name its actual pinned deployment. The adapter owns its authentication. No credential belongs in this file or its arguments. The internal [reviewer adapter](reviewer.md) sends one complete JSON request on stdin with LF/EOF and requires the exact protocol reply; simply naming a model CLI does not make it an adapter. MYC-14 governs the request/reply, literal argv, input hash, identity, retry, timeout and process cleanup contracts. Adapter code, helpers, prompts or nonsecret configuration changes require a new immutable revision.

```toml
[drifts]
review_command = ["~/bin/example-review-adapter", "--config", "~/literal-config.toml"]
review_provider = "example-provider"
review_model = "example-model-2026-10-01"
review_revision = "example-adapter-v1"
```

The path in the third argv member remains exactly `~/literal-config.toml`; its interpretation belongs to that independent adapter.
