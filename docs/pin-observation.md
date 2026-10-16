# Fresh disk observations for evidence pins

`DiskPinObservation(connection, settings, dependant_ref, declaration)` is a
private observation factory. It accepts the one immutable `SettingsSnapshot`
already read for the invocation; it never reloads the settings file, stores a
settings copy, adds a setting or reads a credential. No public command or
provider call is part of this adapter.

Call `expected = observation.observe()` and pass `observation.reread` to
`EvidenceStore.pin` with the original declaration and explicit authorization.
The evidence guard calls this callback under the sorted repository pass/removal
locks before opening its atomic pin transaction. The adapter itself writes
nothing and takes no independent mutation lock.

Every observation reads a new checked disk `SourceResolver.from_store` catalog
and performs a fresh complete `capture_repository` for the enabled dependant
and source repositories. It supplies no previous capture, cached catalog or
reused parse. The original source spelling is resolved for source selection;
the original dependant spelling must resolve to one mutation endpoint. Invalid,
missing, disabled, ambiguous or index-only input cannot become a pin through a
qualified-address substitution.

For an ingest-authorized recognized rename or normalized-equivalent edit, use
`observe_inheritance()` and pass `reread_inheritance` to
`EvidenceStore.inherit_pin`. This path returns `InheritanceInputs`, freshly
validates only the dependant's disk file/endpoint and takes owner-only guards.
It still reads a fresh complete catalog and resolves the original source
declaration for guard/fault metadata. A missing, disabled or invalid source does
not require current source rows/files, and its current bytes are never captured
as a replacement baseline. The evidence layer verifies the dependant's recorded
equivalence and retains the original source snapshots, comparison, membership,
declaration and capture audit in the inherited manifest. A changed dependant
observation refuses inheritance before writing anything.

All current captured files participate in raw path checks, including files not
yet indexed. A new different file under another root therefore invalidates an
unqualified declaration even when the old indexed target is unchanged. A
qualified declaration continues to select its own root. These checks assign no
new stable identities and reconcile no store rows.

Required files must have the same complete original bytes/hash and the same
actual current alias set as the indexed files. The indexed primary may remain
primary while it is a current alias, even when first-discovery root precedence
would choose differently. Fresh Markdown/code chunks must reproduce stored
names, kinds, exact text, spans and body/title projections. Supported recorded
comparisons are checked rather than replaced. A class family must include all
current parsed family members. A file-wide non-UTF-8 selection retains complete
bytes; it receives no lossy text decoding. Exact NUL-containing UTF-8 bodies
remain bytes throughout the resolver/observation boundary.

After capture, every required alias is read again through no-follow parent/file
descriptors. The adapter verifies every byte, regular-file status and unchanged
descriptor observations, and records root/file device/inode, size, mode and
modification/change times in the separate guard set. Before and after the whole
observation it also checks every configured path spelling that each raw ref can
reach, including an absent spelling. This catches a new collision, deletion or
rebind while capture and final reads run. Symlinks below configured roots are
excluded; configured root symlinks resolve freshly and their targets are guarded.
Cancellation closes all open descriptors and prevents pin writes.

`PinInputs` carries the same invocation settings object, complete exact indexed
versions, the fresh full catalog/raw resolution, source/dependant complete-file
guards, canonical alias metadata and current disk observation signatures.
`EvidenceStore.pin` compares the expected and locked observations, then rechecks
stored exact row bindings in its transaction. A changed observation is visibly
`changed_since_ingest`; the caller ingests and retries. The adapter never rewrites
a file, chooses another location or renews a baseline itself. Changes after the
last observation remain changes for the next ordinary detection pass, as MYC-16
specifies.

Only disk adapters are supported. Branch, stash and generated kinds are refused
before any store read. The shared capture API currently reads local Git locations
internally as well as disk. This adapter consumes only its disk location and
conservatively requires the complete capture to succeed; an independent disk-only
capture entry point remains pending. Existing safe read-only Git boundaries,
capture scan/ignore rules and finite child cancellation/deadlines still apply.

The current resolver does not expose ingestion-time physical file/root
observations. Consequently a same-byte physical rebind that predates the initial
expected observation cannot be compared to the original ingestion inode here.
Re-observation detects such changes after the expected observation. Persistent
physical identity checks belong to the complete capture/ingest metadata consumer.
Complete ingest authorization and public confirmation/generated/relation flows
remain unfinished. Configured-store checks verify the scoped observation/pin APIs.

The focused checks use real private temporary files and explicit SQL seams,
including the actual `EvidenceStore.pin` callback path. They declare MYC-13.15
only and establish no owned store requirement or Build claim. They access no live
database, provider, Keychain, owner settings or owner corpus. A separate genuine
MYC-16.13 store candidate uses the gate's default disposable product fixture,
real temporary disk roots and both actual reader/pin callbacks. It checks an
exact roundtrip and refuses a subsequent full-file-only change with unchanged
stored section text and no new baseline writes. The configured gate executes this
method and registers its MYC-16.13 proof; full command and working-Build
qualification remain separate.
