# Origin Links and coverage

An Origin Link states what a chunk rests on. It is a claim, with its method, confidence score and band, author, recording time and any retained review. It does not prove that code conforms to a requirement. Links live only in the Index Store, on ordinary asserted dependencies; Mycel writes no source annotation or ledger file.

## State a link

```sh
mycel justify 'garden:@code/src/water.py#water' 'garden:@artifact/specs/water.md#GDN-1.2' --by maintainer
mycel justify --file /tmp/garden-pairs.jsonl --by maintainer
```

An Entity URI can replace either address. Requirement and decision Origins are returned as their UUID-based Entity URIs; another Origin uses its canonical Mycel address. The dependant is one current disk chunk. A whole file or a class family can be an Origin, retaining its complete selection. Generated selections, missing or ambiguous Origins and changes since the last ingest are refused; ingest explicitly before retrying a changed input.

The bulk file is UTF-8 JSON lines, with one object per nonempty line:

```json
{"chunk":"garden:@code/src/water.py#water","origin":"garden:@artifact/specs/water.md#GDN-1.2"}
```

Each object has exactly these two string fields. Duplicate fields, unknown fields and duplicate exact pairs are refused. Every pair resolves before any assertion, and all assertions, metadata, pins, verification evidence and applied activity share one transaction. A late failure rolls the entire batch back.

The single reply contains `chunk`, `chunkVersion`, `origin`, `link` and the ordinary `verification`. The batch reply is `{ justifications: [...] }` in input order. Pairs for one chunk share one final verification covering all of that chunk's links. A direct statement uses `method: stated`, `confidenceScore: 1` and `confidence: asserted`; its author defaults to the operating-system user. A retained review survives a repeated statement, and no review is invented. `refs` includes these assertions with `originLink`; `stale` and `verifications` show the ordinary result.

## Find work

```sh
mycel origins --repo garden --missing
mycel origins --repo garden --path src --changes
mycel origins --repo garden --unresting --no-fresh
```

Normal use performs one scoped ingest, then a read-only query. It makes no model call and does not embed. `--no-fresh` uses only stored rows. The reply contains `scope` (repository, disk location, normalized paths and changes flag), `chunks` with each chunk's list of links, and optional `unresting` entities. A nonempty missing list and an empty result both return 0. Input and operational failures use ordinary error statuses. No gate or hook is installed.

`--path` repeats and matches complete path components. A single chunk reference restricts the report to that chunk in the selected repository. `--unresting` lists requirements and decisions with no current dependant through an Origin Link. Constraint requirements can record why nothing should rest on them:

```sh
mycel origins --needs-nothing 'garden:@artifact/specs/water.md#GDN-1.3' --reason 'A constraint checked by the conformance test.'
mycel origins --clear-needs-nothing 'garden:@artifact/specs/water.md#GDN-1.3'
```

The mark holds its reason, author and time on the requirement. It creates no dependency or verification, survives ingest and suppresses only the unresting entry.

## Work in the calling clone

List additional checkouts in `repos.<name>.code_clones` and the read-only baseline in `readonly_root`; see the [settings guide](settings.md). Commands inside a listed clone use that checkout, sharing logical identities and equal exact versions with the primary checkout while retaining independent locations and policy. `--changes` compares the calling disk versions with retained local `refs/heads/main` in the read-only clone. Ingest that baseline first. The comparison is an Index Store query and never invokes Git.

The owner backs up PostgreSQL for durable statements and evidence. Mycel has no separate Origin Link backup command; see the [store guide](store.md).
