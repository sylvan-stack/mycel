# Lossless document and code splitting

The internal splitters prepare logical chunks for ingest. They read complete
UTF-8 text and perform no filesystem, database, credential or provider access.
Complete public ingest consumes these splitters through checked stored identity
reconciliation. They preserve logical text independently of embedding input limits.

Markdown sections start at headings outside standard backtick or tilde fences,
including fences inside list and quote containers. Opaque HTML blocks and
comments suppress heading recognition until their supported terminator.
Each heading owns its line and text through the next heading of any level;
subsections are separate chunks. Text before the first heading remains a
preamble. Top-level ATX and setext forms are supported; inline title markup is
retained literally. Heading paths join ancestors with ` > `, and repeated paths
receive disambiguating numbers without colliding with literal heading names.
An empty joined heading path receives the addressable name `<untitled>`; its
actual empty parsed title and exact text, body and spans are preserved. Literal `<untitled>`
headings use the same collision allocation, while nonempty nested paths retain
their literal spelling. A blank line followed by a setext underline is not a
heading and remains in the preamble.

A valid leading YAML mapping is read with pinned `PyYAML==6.0.3` and omitted
from chunk text. The result retains its original text/span and immutable parsed
settings. Unsafe tags, repeated or nontext keys and recursive aliases are
diagnosed. Invalid, unclosed or non-mapping frontmatter remains in the document's
complete chunk coverage with a visible diagnostic.

Each Markdown chunk retains exact text/body, parsed title/path, original line
and half-open byte spans, and an exact snapshot SHA-256. Comparison hashes are
separate: SHA-256 over NFKC-normalized UTF-8, Unicode whitespace collapsed to
single spaces and outer whitespace removed. Body comparison excludes the
heading; title comparison covers the parsed title. The comparison revision and
Unicode version are recorded. Rewrapping can preserve comparison while changing
the exact snapshot.

Python uses its syntax tree. TypeScript, TSX and JavaScript use pinned official
tree-sitter grammars. Functions, classes as headers plus methods, and supported
language declarations receive language, kind, symbol and original byte/line
spans. Decorators and leading comments remain with their symbols. Loose runs
use `<before symbol>` or `<end>`; duplicate symbols receive suffixes. Inserting
an unrelated loose run does not renumber existing module names.

Svelte uses the accepted script/style block pattern and keeps markup between
blocks. Shell, property lists and Swift remain whole-file chunks. All fifteen
configured default code endings are recognized. Parse failure returns one
complete whole-file chunk. Every structural result partitions the original
bytes without gaps, overlap, trimming or truncation.

Source declarations retain the frontmatter `sources` entries and visible
`<!-- sources: ... -->` comments in document order. A frontmatter declaration
belongs to the first logical chunk; a comment belongs to its containing chunk.
Each entry keeps its literal spelling, physical line and declaration origin,
including duplicates and malformed addresses. Fences, indented code, inline
code and opaque raw HTML do not create declarations. Known role, status,
heartwood and generated fields receive explicit validation; unrelated YAML
keys remain ordinary document metadata.

The pure address parser accepts both literal legacy `repository:path#name`
forms and portable `repository:@code/path#name`, `repository:@artifact/path#name`
or `repository:@index/path#name` forms. Portable components decode UTF-8 percent
escapes once, preserve case and reject absolute/traversal paths, encoded path
separators and malformed escapes. Legacy percent signs remain literal. The
formatter escapes component delimiters so parsing its output preserves the
same repository, root, path and optional name.

The shared typed resolver reads one checked, repeatable PostgreSQL snapshot for
disk or an explicitly named branch/stash location. It returns whole-file bytes,
one chunk or an ordered class family; a class read returns its header. Mutation
endpoints require one chunk, and index-only text is eligible only for reads.
Overlapping-root aliases share identifiers and the retained primary address;
distinct files at one bare path produce qualified ambiguity candidates. Unknown
and disabled repositories are invalid, while missing enabled targets remain
unresolved. Located names, roots and extraction spans override version metadata
when text survives a move. Invalid hashes, spans or catalog metadata refuse the
read rather than substituting another location's text.

The authoritative behavior is in MYC-1/MYC-2/MYC-16. The configured real-store
proofs now cover location-owned declaration retention and retries, physical
root alias/move bindings and guarded typed pins; see [stored Source Refs](source-refs.md).
Complete ingest/dependency application, arbitrary file identity reconciliation
and public read/ref command replies remain separate integration work.

## Requirement and decision rows (MYC-17)

A row of a pipe table whose first cell is exactly a human id, `MYC-2.13` or
`MYC-D45`, followed by an HTML comment with the row's UUID, is an entity row.
`split_markdown` returns them in `document.entities`, one `EntityRow` per row:
its kind `req` or `dec`, the UUID, the human id as its name, the title (the
second cell of a requirement, the Question cell of a decision), the exact
physical row with its line ending and byte span, its line, its position among
the table's body rows, the section that holds it, and the metadata read under
the table's header: the chapter's frontmatter status or `withdrawn`, `decided`
or `open` with `decidedAt`/`decidedBy` from an Outcome that begins `Decided
<date> by <who>`, `verifiedBy`, `fromV1` (the `From v1` or former `Origin`
column) and the chat Entity URIs of a Discussion cell. Section chunks are
unchanged: they keep their complete text, byte coverage and hashes, so an edit
to a row changes the section's hashes as before and gives the row its own new
exact version.

Rows inside code fences, rows without a header and delimiter line, and first
cells with more than the id (`MYC-D1 · What language…`) are prose. A recognised
row without a UUID is the diagnostic `entity_missing_uuid` and two rows with
one UUID are `entity_repeated_uuid`, each with its line; neither becomes an
entity. The parse cache serializes `EntityRow` like the other parser values.
