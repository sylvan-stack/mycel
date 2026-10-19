# Reading exact indexed chunks

`mycel read` returns one complete current indexed chunk: a code symbol, a
document section under either configured root, a summary, or an overview
section. A class name selects its header alone. Stored text is returned even
when its file is absent or unreadable; optional context comes from a readable
code file and never replaces the indexed text.

```sh
mycel read 'cellar:@code/src/net/retry.py#RetryPolicy.allow'
mycel read 'cellar:src/net/retry.py#allow' --context 5
mycel read 'cellar:@artifact/docs/net.md#Retry%20policy'
mycel read 'handbook:@index/summaries#1%2F7'
mycel read 'cellar:@index/overview#src%2Fnet'
mycel read --id '<search-result-id>' --no-fresh
```

Qualified addresses use the central [source resolver](source-refs.md).
Legacy literal places remain valid when unambiguous. Short method names and
unique bare section titles are accepted. An unqualified path matching distinct
physical files is ambiguous before its heading is selected. Freshly captured root or short-name collisions
are refused even when the earlier index had one match. An index namespace
and a real file sharing a path never silently select one another. Overlapping
aliases of the same physical file retain one primary canonical address.
`--repo` selects at most one enabled repository for short places or identifiers;
qualified places already name their repository.

No match or several matches returns `invalid_input`; an ambiguity includes up
to 20 root-aware candidate places. An unknown registration returns
`unknown_repository` and a disabled repository returns `refused`. Only current
disk or generated locations can be read; branch/stash-only text and retained
evidence blobs are not current chunks. A known retained identifier seeds its
repository check even when its chunk currently has only branch/stash locations.
A normal fresh read can therefore observe a file restored onto disk; an absent
chunk still fails the final current selection. `--no-fresh` requires a current
indexed disk/generated match immediately.

Before the final read, the command checks and ingests changes in the requested
repository and recursively enabled repositories of that chunk's explicit
upstream sources under `search.freshness_seconds`. Required upstreams do not
become returned chunks or shared-document suppliers. Busy, failed, interrupted,
refused or time-limited work falls back to the current index and retains every
known completed/pending repository and reason. `--no-fresh` bypasses the entire
check and performs no freshness writes. Neither path generates text, embeds,
classifies, renews unchanged pins or confirms claims.

The schema-1 reply contains `id`, `repository`, `origin`, actual `root`, relative
`path`, canonical qualified `address`, `name`, optional `kind`/`lines`, stored
`text` and `cut`. It includes `stale`, every source/path `staleReasons`,
`heartwood`, `dependencyCheck` with `complete` and ref `faults`, and a readable
absolute `file` or `unreadable` reason. Checkout Markdown keeps document origin
and code root. `freshness` contains `checked`, `finished`, total `ingested` and
per-repository `state`, `ingested` and a reason for every non-done state.
An absent stale mark with an incomplete dependency check does not verify current
text or sources.

Every reply has `documents`, an array of all document sections joined directly
to a code chunk by a declared or asserted dependency. A link contains `section`
(the canonical root-qualified place), `direction` (`source` when code rests on
the section, `dependant` when the section rests on code) and `edge` (`declared`
or `asserted`). Whole-file and class-family refs include each selected code
chunk. The list has no two-section limit and needs no vectors or query. Current
stored disk endpoints count even when the code is stale; branch-only endpoints,
relations, summaries, overviews and code-to-code edges do not. Document and
index-only reads, and code with no describing section, return `documents: []`.

<!-- sources:
mycel:@code/src/mycel/_document_links.py#document_links
mycel:@code/src/mycel/_read_store.py#read_from_store
-->

`--context N` accepts 0 through 50 lines on each side of a file-backed code
symbol. Without it the reply has no context. Document/generated chunks receive
no file context. The text is bounded to 5 MiB of UTF-8 without cutting a code
point, with `cut: true` when truncation occurs; context does not alter the
stored chunk text or identity.

`mycel info` lists this Build's command names in `commands` and advertises
`readReply: 1`. Help identifies currently implemented handlers and read options.
There is no separate capabilities command. Complete installed distribution,
summary creation and Drift execution keep their own
task requirements.

Local classification bookkeeping shares the original freshness allowance.
It makes no Jev or reviewer calls. After successfully checked sources it updates
quiet-period eligibility and may apply a completed exact matching result through
the same canonical guards. `classificationCheck` reports whether this local work
was checked and complete, its pending stages and reused applications. Busy,
expired or unchecked sources remain explicit; `--no-fresh` performs none of this
work. Stored stale reasons keep their current classification evidence without
turning an incomplete dependency check into a current verification.

## Requirements and decisions (MYC-17)

A requirement or decision row is a chunk of kind `req` or `dec` whose
identifier is the row's UUID. `mycel read` accepts its Entity URI,
`[req:<uuid>:<title-base64>]` or `[<repo>:dec:<uuid>:<title>]`, and resolves
it by the UUID alone; a kind tag that does not match the entity is refused
with `invalid_input`, as is a `cht` URI, which names no chunk. The same row is
read by its full address with the human id as the name,
`mycel:@artifact/specs/02-provenance-and-freshness.md#MYC-2.13`, by the human
id within its file, or by `--id <uuid>`.

```sh
mycel read '[req:9b6984cc-db34-4a84-b948-0eaefbea916a:bWFyayBhIGNodW5rIHN0YWxl]'
mycel read 'mycel:specs/02-provenance-and-freshness.md#MYC-2.13' --no-fresh
```

The reply has `origin: "document"`, `kind: "req"` or `"dec"`, the row's exact
text and lines, and an `entity` object with `kind`, `uuid`, `id`, `uri` (with
the repository's name as the repo code), `title`, `status` and the row's
metadata. For a decision it also carries `discussion`: one entry per chat Entity
URI of the Discussion cell, read as data from the Arbol database that the
`[discussions]` settings name in one read-only transaction, with the chat's
`title` and its `messages` in order, replaced Exchanges left out; or
`available: false` with the reason when the settings name no address, the
database cannot be reached or the chat does not exist. The read succeeds either
way and writes nothing there.
