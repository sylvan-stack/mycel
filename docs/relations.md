# Relations and verification

A relation says to review one chunk when another changes. It grants no source
authority or derived role and never enters dependency edges, search bridges or
`documentedIn`. Relations may point both ways or form cycles. Each direction
must be declared or asserted explicitly.

```markdown
## Reply format

The reply repeats the request identifier.

<!-- related:
cellar:@artifact/docs/api.md#Request format
cellar:@code/request.py#Request
-->
```

Only document sections declare relations. The `related` comment shares the
Source Ref forms and CommonMark code/link exclusions of `sources` comments;
each nonempty line is one reference. Frontmatter `related` and code comments
declare nothing. Every original line and occurrence survives parsing, including
malformed or unclosed comments. Enabled, registered sources may select one
chunk, complete file bytes, or a class header with all its members.
Equivalent valid occurrences share one pin. A malformed duplicate keeps its
own reported fault without invalidating a valid occurrence of the same ref;
any malformed occurrence still prevents confirmation.

Complete located publication reconciles declarations in the same guarded
transaction as identities, dependency policy and mechanical detection. It
resolves the entire selection, stores exact dependant-owned snapshots and an
immutable membership manifest, and preserves the existing pin for unchanged,
restored, normalized-equivalent or recognized renamed versions. A substantive
dependant edit renews its own relation pins. An edit elsewhere in its file does
not. Historical versions and other locations keep their separate baselines.
A valid source changing between a class family and a single chunk at the same
place preserves the existing pin and reports the changed selection. Missing
members of the pinned family remain `source_removed`, even when the current
source is no longer a class.

`mycel refs [--repo cellar] [--unresolved]` reports declared relations with
`kind: "related"`, exact original occurrences, canonical resolved address and
visible missing, unknown, disabled, malformed or ambiguous faults. Reporting
reads one committed snapshot, never resolves again or writes state.

```sh
mycel relate 'cellar:@artifact/docs/api.md#Reply format' 'cellar:@artifact/docs/api.md#Request format'
mycel relate --remove 'cellar:@artifact/docs/api.md#Reply format' 'cellar:@artifact/docs/api.md#Request format'
```

The first endpoint is the dependant and the second is its source. Both must
resolve to one current disk chunk. A class endpoint selects its header alone;
it does not silently expand the family as a declared relation may. File-wide
and index-only endpoints are invalid. Source and dependant files, settings,
aliases and relevant retained Git locations are reread under repository guards;
changed-since-ingest inputs return `invalid_input` with `changed_since_ingest`.
The command never ingests or writes either source file.

An assertion is held apart from any declared relation between the same ends.
Repeating it, including a qualified or legacy alias, preserves its baseline,
feature rows, evidence and activity. `--remove` withdraws only the exact matching
assertion, including a retained missing source. An absent removal succeeds with
`changed: false`. A missing source without retained ownership uses its explicit
qualified address, or the unique canonical file binding when only its name is
missing. Use a qualified Source Ref when an absent file has no retained binding;
a legacy path cannot establish which root it means.

The reply contains qualified `dependant` and `source` places, exact
`dependantVersion`, `action: "assert" | "remove"`, `changed`, and `members`.
Assertions also return `baselineManifest`. Numbered Builds record actual
`relate` activity and its exact final reply atomically with the relation; final
input checks after activity attachment roll back late changes.

Detection compares pinned member hashes and complete membership after both
corpora. A direct change records `related_changed`; a missing member records
`source_removed`. Restored matching bytes remove the answered reason. Relation
warnings stay on the direct dependant, including when that dependant has its
own dependency children. Busy or unchecked owners retain their previous marks
and report pending work. No model or provider runs. A substantive edit or the
transaction-bound confirmation hook renews direct pins and withdraws a
previously resolved asserted source that has been deleted. A declared reference
to the same missing source remains a visible fault. Public confirmation composes the same guarded policies with independent verification evidence.

The [source-reference guide](source-refs.md), [evidence guide](evidence.md) and
[reconciliation guide](reconciliation.md) describe the shared resolver,
immutable evidence and capture guards. Complete public ingest uses these APIs.
Stale listing and search retain their implementation tasks.

## Recorded verification

```sh
mycel confirm 'cellar:@artifact/docs/api.md#Reply format' --by ana --how read
mycel verifications --repo cellar
mycel verifications --repo cellar --history
```

Confirmation selects one exact current disk chunk and rereads its complete
physical file, current settings, every dependency/relation selection and its
membership under repository guards. It never ingests implicitly. Changed bytes
since ingest, new invalid refs, an unavailable required guard, or a late input
change refuse the whole transaction. A previously resolved deleted source may
be withdrawn; any surviving declared ref remains a visible fault. Pin renewal,
exact immutable record-owned evidence, mechanical reason updates and numbered
Build activity share one rollback boundary. Remaining upstream reasons survive.
Source-free fault-free chunks can be confirmed; generated text cannot.

Each record stores the exact dependant bytes and hash, checked selection
manifests, every source/related member's exact hash and comparison hash, voucher,
method and time. `--by` defaults to the login name; `--how` defaults to `read` and
also accepts `check`. Both methods record a statement about those exact inputs;
Mycel computes no confidence score or upstream certification. The public reply
is the complete `Verification` described in the [command guide](command-line.md).

Listing reads one enabled repository in one read-only repeatable snapshot. It
checks the newest record for each exact current disk dependant version against
current dependant/source bytes, enabled eligibility and complete membership.
Missing or presently uncheckable inputs make `current` false. Default output
contains only applicable records; `--history` includes all retained records,
sorted by canonical root/path/name, then newest time and record ID. It performs
no ingest, freshness pass, evidence write or provider call and succeeds empty.

Verification rows belong to logical chunks in store format 2. Their exact
version descriptor and evidence are immutable record data: collecting an old
unlocated version leaves history intact, while deleting its owning logical chunk
or repository releases that record's evidence. Independent record ownership
keeps old manifests and snapshots after live pins are replaced or sources are
deleted. There is no age limit and retained history is not searchable old text.
Only explicit `init` migrates format 1; malformed or unverifiable legacy record
evidence refuses migration atomically, preserving the old schema and generation.
